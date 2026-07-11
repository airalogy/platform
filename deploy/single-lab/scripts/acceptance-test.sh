#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command curl
require_command jq
require_env_file

site_url="$(env_value SITE_URL)"
api_url="${site_url%/}/api"
setup_code="$(env_value INITIAL_ADMIN_TOKEN)"
owner_email="${SMOKE_OWNER_EMAIL:-owner@acceptance.example.com}"
owner_password="${SMOKE_OWNER_PASSWORD:-AcceptanceOwner123}"
member_email="${SMOKE_MEMBER_EMAIL:-member@acceptance.example.com}"
member_password="${SMOKE_MEMBER_PASSWORD:-AcceptanceMember123}"
member_new_password="${SMOKE_MEMBER_NEW_PASSWORD:-AcceptanceMember456}"
curl_args=()

case "$site_url" in
  http://localhost | https://localhost | http://localhost:* | https://localhost:* | \
    http://127.0.0.1 | https://127.0.0.1 | http://127.0.0.1:* | https://127.0.0.1:*)
    curl_args+=(--noproxy '*')
    ;;
esac

request() {
  curl "${curl_args[@]}" --silent --show-error --fail-with-body "$@"
}

status="$(request "$api_url/instance")"
[[ "$(jq -r '.single_lab' <<<"$status")" == "true" ]] || die "instance is not in single-Lab mode"
[[ "$(jq -r '.initialized' <<<"$status")" == "false" ]] || die "acceptance test requires a fresh, uninitialized deployment"

info "Bootstrapping owner account..."
bootstrap="$(request \
  -H 'Content-Type: application/json' \
  -X POST \
  -d "$(jq -n \
    --arg setup_token "$setup_code" \
    --arg username acceptance_owner \
    --arg email "$owner_email" \
    --arg name 'Acceptance Owner' \
    --arg password "$owner_password" \
    '{setup_token:$setup_token,username:$username,email:$email,name:$name,password:$password,confirm_password:$password}')" \
  "$api_url/instance/bootstrap")"
owner_token="$(jq -r '.token' <<<"$bootstrap")"
lab_id="$(jq -r '.lab.id' <<<"$bootstrap")"
lab_uid="$(jq -r '.lab.uid' <<<"$bootstrap")"

projects="$(request -H "Auth-Token: $owner_token" "$api_url/projects?lab_uid=$lab_uid")"
jq -e '.projects | any(.uid == "lab_protocols")' <<<"$projects" >/dev/null || die "default private project was not created"

public_project_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X POST \
  -d "$(jq -n --arg lab_id "$lab_id" '{lab_id:$lab_id,name:"Public test",uid:"public_test",type:2}')" \
  "$api_url/projects")"
[[ "$public_project_code" == "400" ]] || die "single-Lab mode unexpectedly allowed a public Project"

owner_project_invite_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X POST \
  -d "$(jq -n --arg email owner-role@acceptance.example.com '{email:$email,lab_role:3,project_role:1}')" \
  "$api_url/instance/invitations")"
[[ "$owner_project_invite_code" == "400" ]] || die "invitation unexpectedly granted default Project ownership"

info "Creating and accepting a member invitation..."
invitation="$(request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X POST \
  -d "$(jq -n --arg email "$member_email" '{email:$email,lab_role:3,project_role:40}')" \
  "$api_url/instance/invitations")"
invite_url="$(jq -r '.url' <<<"$invitation")"
invite_token="${invite_url##*token=}"

signup="$(request \
  -H 'Content-Type: application/json' \
  -X POST \
  -d "$(jq -n \
    --arg username acceptance_member \
    --arg email "$member_email" \
    --arg name 'Acceptance Member' \
    --arg password "$member_password" \
    --arg invite_token "$invite_token" \
    '{username:$username,email:$email,name:$name,password:$password,confirm_password:$password,invite_token:$invite_token}')" \
  "$api_url/signup")"
member_token="$(jq -r '.token' <<<"$signup")"
member_id="$(jq -r '.user.id' <<<"$signup")"

lab_after_invite="$(request -H "Auth-Token: $owner_token" "$api_url/labs/uid/$lab_uid")"
[[ "$(jq -r '.data.users_count' <<<"$lab_after_invite")" == "2" ]] || die "Lab member count is incorrect after invitation acceptance"

member_projects="$(request -H "Auth-Token: $member_token" "$api_url/projects?lab_uid=$lab_uid")"
jq -e '.projects | any(.uid == "lab_protocols")' <<<"$member_projects" >/dev/null || die "invited member cannot access the default project"

permission_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $member_token" \
  -X POST \
  -d "$(jq -n --arg email blocked@acceptance.example.com '{email:$email,lab_role:3,project_role:40}')" \
  "$api_url/instance/invitations")"
[[ "$permission_code" == "403" ]] || die "ordinary member unexpectedly created an invitation"

info "Checking password change session revocation..."
password_change="$(request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $member_token" \
  -X PUT \
  -d "$(jq -n \
    --arg current_password "$member_password" \
    --arg password "$member_new_password" \
    '{current_password:$current_password,password:$password,confirm_password:$password}')" \
  "$api_url/instance/account/password")"
new_member_token="$(jq -r '.token' <<<"$password_change")"

old_token_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H "Auth-Token: $member_token" \
  "$api_url/users/api_key")"
[[ "$old_token_code" == "401" ]] || die "old member JWT was not revoked after password change"
request -H "Auth-Token: $new_member_token" "$api_url/users/api_key" >/dev/null

info "Checking administrator-issued one-time reset link..."
reset_link="$(request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X POST \
  -d "$(jq -n --arg user_id "$member_id" '{user_id:$user_id}')" \
  "$api_url/instance/password-reset-links")"
reset_url="$(jq -r '.url' <<<"$reset_link")"
reset_token="${reset_url##*token=}"
reset_password="AcceptanceMember789"
request \
  -H 'Content-Type: application/json' \
  -X POST \
  -d "$(jq -n --arg password "$reset_password" '{password:$password,confirm_password:$password}')" \
  "$api_url/instance/password-resets/$reset_token" >/dev/null

replay_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -X POST \
  -d "$(jq -n --arg password "$reset_password" '{password:$password,confirm_password:$password}')" \
  "$api_url/instance/password-resets/$reset_token")"
[[ "$replay_code" == "404" ]] || die "password reset token was reusable"

final_login="$(request \
  -H 'Content-Type: application/json' \
  -X POST \
  -d "$(jq -n --arg email "$member_email" --arg password "$reset_password" '{email:$email,password:$password}')" \
  "$api_url/signin_by_email")"
final_member_token="$(jq -r '.token' <<<"$final_login")"

info "Checking manager invitation limits and demotion revocation..."
request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X PUT \
  -d "$(jq -n --arg user_id "$member_id" '{user_id:$user_id,role:2,alias:""}')" \
  "$api_url/labs/$lab_id/users/$member_id" >/dev/null

manager_invitation="$(request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $final_member_token" \
  -X POST \
  -d "$(jq -n --arg email demoted-manager-invite@acceptance.example.com '{email:$email,lab_role:3,project_role:40}')" \
  "$api_url/instance/invitations")"
manager_invite_url="$(jq -r '.url' <<<"$manager_invitation")"
manager_invite_token="${manager_invite_url##*token=}"

manager_role_invite_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $final_member_token" \
  -X POST \
  -d "$(jq -n --arg email manager-role@acceptance.example.com '{email:$email,lab_role:2,project_role:40}')" \
  "$api_url/instance/invitations")"
[[ "$manager_role_invite_code" == "403" ]] || die "manager unexpectedly invited another Lab manager"

request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X PUT \
  -d "$(jq -n --arg user_id "$member_id" '{user_id:$user_id,role:3,alias:""}')" \
  "$api_url/labs/$lab_id/users/$member_id" >/dev/null

demoted_invite_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  "$api_url/instance/invitations/$manager_invite_token")"
[[ "$demoted_invite_code" == "404" ]] || die "demoted manager retained an active invitation"

pending_reset_link="$(request \
  -H 'Content-Type: application/json' \
  -H "Auth-Token: $owner_token" \
  -X POST \
  -d "$(jq -n --arg user_id "$member_id" '{user_id:$user_id}')" \
  "$api_url/instance/password-reset-links")"
pending_reset_url="$(jq -r '.url' <<<"$pending_reset_link")"
pending_reset_token="${pending_reset_url##*token=}"

info "Checking complete permission cleanup when a member is removed..."
request \
  -H "Auth-Token: $owner_token" \
  -X DELETE \
  "$api_url/labs/$lab_id/users/$member_id" >/dev/null
removed_projects="$(request -H "Auth-Token: $final_member_token" "$api_url/projects?lab_uid=$lab_uid")"
[[ "$(jq -r '.total_count' <<<"$removed_projects")" == "0" ]] || die "removed member retained project access"
removed_lab_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  -H "Auth-Token: $final_member_token" \
  "$api_url/labs/uid/$lab_uid")"
[[ "$removed_lab_code" == "403" ]] || die "removed member retained Lab detail access"
revoked_reset_code="$(curl "${curl_args[@]}" --silent --output /dev/null --write-out '%{http_code}' \
  "$api_url/instance/password-resets/$pending_reset_token")"
[[ "$revoked_reset_code" == "404" ]] || die "removed member retained an active password reset link"

info "Checking operator-only owner recovery..."
operator_reset_url="$("$SCRIPT_DIR/operator-reset-link.sh" "$owner_email")"
operator_reset_token="${operator_reset_url##*token=}"
operator_reset_info="$(request "$api_url/instance/password-resets/$operator_reset_token")"
[[ "$(jq -r '.email' <<<"$operator_reset_info")" == "$owner_email" ]] || die "operator reset link does not target the owner"

info "Checking that one-time credentials were not written to service logs..."
service_logs="$(compose logs --no-color api-server web)"
for secret in "$setup_code" "$invite_token" "$manager_invite_token" "$reset_token" "$pending_reset_token" "$operator_reset_token"; do
  if grep -F "$secret" <<<"$service_logs" >/dev/null; then
    die "a one-time credential was found in service logs"
  fi
done

info "Single-Lab acceptance test passed."
