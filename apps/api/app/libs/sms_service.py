import json
import logging

from alibabacloud_dysmsapi20170525 import models as models2017
from alibabacloud_dysmsapi20170525.client import Client as Client2017
from alibabacloud_dysmsapi20180501 import models as models2018
from alibabacloud_dysmsapi20180501.client import Client as Client2018
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from app.config import config

logger = logging.getLogger("app")

# for china
ali_client2017 = Client2017(
    open_api_models.Config(
        access_key_id=config.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=config.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="dysmsapi.aliyuncs.com",
    )
)

# for global
ali_client2018 = Client2018(
    open_api_models.Config(
        access_key_id=config.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=config.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        endpoint="dysmsapi.ap-southeast-1.aliyuncs.com",
    )
)


async def send_sms(phone_number: str, template_code: str, template_param: dict):
    send_sms_request = models2017.SendSmsRequest(
        phone_numbers=phone_number,
        sign_name=config.ALIBABA_CLOUD_SMS_SIGN_NAME,
        template_code=template_code,
        template_param=json.dumps(template_param, ensure_ascii=False),
    )
    try:
        await ali_client2017.send_sms_with_options_async(
            send_sms_request, util_models.RuntimeOptions()
        )
    except Exception as error:
        logger.error(f"send sms error: {error}")


async def send_sms_to_global(phone_number: str, verify_code: str):
    send_sms_request = models2018.SendMessageToGlobeRequest(
        to=phone_number,
        from_=config.ALIBABA_CLOUD_SMS_SENDER_ID,
        message=f"Airalogy: Your verification code is {verify_code}. It will expire in 10 minutes.",
    )
    try:
        await ali_client2018.send_message_to_globe_with_options_async(
            send_sms_request, util_models.RuntimeOptions()
        )
    except Exception as error:
        logger.error(f"send global sms error: {error}")


async def send_verify_code(phone_number: str, verify_code: str):
    if phone_number.startswith("86"):
        await send_sms(
            phone_number,
            config.ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE,
            {"code": verify_code},
        )
    else:
        await send_sms_to_global(phone_number, verify_code)
