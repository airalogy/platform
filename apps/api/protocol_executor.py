import importlib
import importlib.util
import json
import logging
import os
import sys
import tomllib
from datetime import timedelta
from typing import get_args, get_origin

from airalogy.assigner import DefaultAssigner
from airalogy.ingest import import_records as import_airalogy_records
from airalogy.markdown import extract_assigner_blocks, generate_model, parse_aimd
from airalogy.markdown.errors import AimdParseError
from pydantic import TypeAdapter, ValidationError, create_model

# 创建logger
logger = logging.getLogger("protocol_executor_logger")
logger.setLevel(logging.DEBUG)

# 创建文件处理器
file_handler = logging.FileHandler("protocol_executor.log")
file_handler.setLevel(logging.DEBUG)

# 创建格式器
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 保存原始的标准输出
original_stdout = sys.stdout


# NullStream, do nothing when write
class NullStream:
    def write(self, s):
        pass


# set stdout to NullStream
sys.stdout = NullStream()

timedelta_adapter = TypeAdapter(timedelta)


def deep_merge(dict1: dict, dict2: dict):
    """Merge two dictionaries recursively."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def extract_vars(aimd_content: str) -> dict:
    templates = parse_aimd(aimd_content)["templates"]
    return {
        "vars": templates.get("var", []),
        "quizzes": templates.get("quiz", []),
        "steps": templates.get("step", []),
        "checks": templates.get("check", []),
        "ref_vars": templates.get("ref_var", []),
        "ref_steps": templates.get("ref_step", []),
        "ref_figs": templates.get("ref_fig", []),
        "cites": templates.get("cite", []),
        "assigners": templates.get("assigner", []),
    }


# custom json encoder for timedelta
class RNJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, timedelta):
            return timedelta_adapter.dump_python(obj, mode="json")
        else:
            return json.JSONEncoder.default(self, obj)


def import_module(module_name):
    # 尝试查找模块规格
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        logger.warning(f"module {module_name} not found")
        return None

    try:
        # 从规格创建模块并执行
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module  # 将模块添加到sys.modules缓存中
        spec.loader.exec_module(module)
        return module
    except SyntaxError as e:
        # 捕获语法错误并提供详细信息
        error_msg = (
            f"Protocol module `{module_name.split('.')[-1]}` has syntax error: {e}"
        )
        error_msg += (
            f"\nfile: {e.filename.split('/')[-1]}, line: {e.lineno}, offset: {e.offset}"
        )
        error_msg += f"\nerror code: {e.text}"
        logger.error(error_msg)
        raise ImportError(error_msg)
    except ImportError as e:
        error_msg = (
            f"Import protocol module `{module_name.split('.')[-1]}` fail, error: {e}"
        )
        logger.error(error_msg)
        raise ImportError(error_msg)
    except Exception as e:
        # 捕获其他执行错误
        error_msg = (
            f"Import protocol module `{module_name.split('.')[-1]}` fail, error: {e}"
        )
        logger.error(error_msg)
        raise ImportError(error_msg)


def _load_tmp_aimd_model(protocol_name: str):
    """generate AIMD model for the protocol."""
    protocol_path = f"./protocols/{protocol_name}"
    if not os.path.isfile(f"{protocol_path}/tmp_aimd_model.py"):
        try:
            with open(f"{protocol_path}/protocol.aimd") as f:
                aimd = f.read()
                aimd_model = generate_model(aimd)
                with open(
                    f"{protocol_path}/tmp_aimd_model.py", "w", encoding="utf-8"
                ) as f:
                    f.write(aimd_model)
        except AimdParseError as e:
            raise ValueError(f"Error parsing protocol.aimd: {e}")

    return import_module(f"protocols.{protocol_name}.tmp_aimd_model")


def get_protocol_info(protocol_name: str, params: dict):
    protocol_path = f"./protocols/{protocol_name}"
    # check protocol.aimd file
    if not os.path.isfile(f"{protocol_path}/protocol.aimd"):
        raise ValueError("protocol.aimd file not found in package")

    protocol_toml_path = f"{protocol_path}/protocol.toml"
    # check protocol.toml file
    if not os.path.isfile(protocol_toml_path):
        raise ValueError("protocol.toml file not found in package")

    assigner_path = f"{protocol_path}/assigner.py"
    try:
        with open(f"{protocol_path}/protocol.aimd") as f:
            aimd = f.read()
            fields = extract_vars(aimd)
            aimd_model = generate_model(aimd)
            with open(f"{protocol_path}/tmp_aimd_model.py", "w", encoding="utf-8") as f:
                f.write(aimd_model)
            if not os.path.isfile(assigner_path):
                assigner_code_blocks = [
                    block.get("code", "") if isinstance(block, dict) else block
                    for block in extract_assigner_blocks(aimd)
                ]
                assigner_code_blocks = [
                    block for block in assigner_code_blocks if block
                ]
                if len(assigner_code_blocks) > 0:
                    with open(assigner_path, "w", encoding="utf-8") as f:
                        f.write("\n\n".join(assigner_code_blocks))
    except AimdParseError as e:
        raise ValueError(f"Error parsing protocol.aimd: {e}")
    vars = set([var["name"] for var in fields["vars"]])
    steps = set([step["name"] for step in fields["steps"]])
    checks = set([check["name"] for check in fields["checks"]])

    # read metadata from protocol.toml
    try:
        with open(protocol_toml_path, "rb") as f:
            meta_data = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Error parsing protocol.toml: {e}")
    if "airalogy_protocol" not in meta_data:
        raise ValueError(
            "Invalid protocol.toml, error: airalogy_protocol not found in protocol.toml"
        )
    meta_data = meta_data["airalogy_protocol"]
    # check id, name, version
    if "id" not in meta_data:
        raise ValueError("Invalid protocol.toml, error: id not found in protocol.toml")
    if "name" not in meta_data:
        raise ValueError(
            "Invalid protocol.toml, error: name not found in protocol.toml"
        )
    if "version" not in meta_data:
        raise ValueError(
            "Invalid protocol.toml, error: version not found in protocol.toml"
        )

    # read env vars from .env file
    env_vars_str = ""
    env_file = f"{protocol_path}/.env"
    if os.path.isfile(env_file):
        with open(env_file) as f:
            env_vars_str = f.read()

    schema = {
        "steps": {},
        "vars": {},
        "checks": {},
    }
    # set runtime env vars
    for k, v in params["env_vars"].items():
        os.environ[k] = v

    protocol_module = f"protocols.{protocol_name}"
    # load aimd model
    aimd_model = import_module(f"{protocol_module}.tmp_aimd_model")
    if aimd_model and hasattr(aimd_model, "VarModel"):
        aimd_schema = aimd_model.VarModel.model_json_schema()
    else:
        aimd_schema = {"type": "object", "required": [], "properties": {}}

    # load var model
    var_model = import_module(f"{protocol_module}.model")
    if var_model and hasattr(var_model, "VarModel"):
        model_schema = var_model.VarModel.model_json_schema()
        # check model schema properties should be defined in AIMD
        errors = []
        for key in model_schema["properties"]:
            if key not in vars:
                errors.append(f"Model field `{key}` not defined in AIMD file")
        if errors:
            raise ValueError("\n".join(errors))
    else:
        model_schema = {}

    schema["vars"] = deep_merge(aimd_schema, model_schema)

    assigners = {}
    assigner_graph = None
    assigner = import_module(f"{protocol_module}.assigner")
    if assigner:
        if hasattr(assigner, "Assigner"):
            assigners = assigner.Assigner.all_assigned_fields()
            assigner_graph = assigner.Assigner.export_dependency_graph_to_dict()
        else:
            assigners = DefaultAssigner.all_assigned_fields()
            assigner_graph = DefaultAssigner.export_dependency_graph_to_dict()

        errors = []
        for k, v in assigners.items():
            if "." in k:  # for table subvar
                k = k.split(".")[0]
            if k not in vars and k not in steps and k not in checks:
                errors.append(f"Assigner field {k} not defined in protocol.aimd file")
            for j in v["dependent_fields"]:
                if "." in j:  # for table subvar
                    j = j.split(".")[0]
                if j not in vars and j not in steps and j not in checks:
                    errors.append(
                        f"Assigner dependent field {j} not defined in protocol.aimd file"
                    )
        if errors:
            raise ValueError("\n".join(errors))

    return {
        "meta_data": meta_data,
        "fields": fields,
        "aimd": aimd,
        "json_schema": schema,
        "assigners": assigners,
        "assigner_graph": assigner_graph,
        "env_vars": env_vars_str,
    }


def var_assign(protocol_name: str, params: dict) -> dict:
    # set environment variables
    for k, v in params["env_vars"].items():
        os.environ[k] = v

    # load assigner
    assigner_module = import_module(f"protocols.{protocol_name}.assigner")
    if assigner_module is None:
        raise ValueError("Protocol Package does not have assigner")

    if hasattr(assigner_module, "Assigner"):
        assigner = assigner_module.Assigner
    else:
        assigner = DefaultAssigner

    # load tmp_aimd_model
    aimd_model = _load_tmp_aimd_model(protocol_name)
    fields = aimd_model.VarModel.model_fields

    # load model
    var_model = import_module(f"protocols.{protocol_name}.model")
    if var_model is not None and hasattr(var_model, "VarModel"):
        fields = deep_merge(fields, var_model.VarModel.model_fields)

    try:
        # dependent_data validation and type convert
        attrs = {}
        for k, v in params["dependent_data"].items():
            if k in fields:
                attrs[k] = (fields[k].annotation, fields[k].default)
            elif "." in k:
                var_table_name, sub_var_name = k.split(".")
                if var_table_name not in fields:
                    raise ValueError(f"Var: {var_table_name} not defined in VarModel")
                if get_origin(fields[var_table_name].annotation) is not list:
                    raise ValueError(
                        f"Var table variable: {var_table_name} must be a list"
                    )
                table_type = get_args(fields[var_table_name].annotation)[0]
                if sub_var_name in table_type.model_fields:
                    attrs[k] = (
                        table_type.model_fields[sub_var_name].annotation,
                        table_type.model_fields[sub_var_name].default,
                    )
                else:
                    attrs[k] = (str, ...)
            else:
                attrs[k] = (str, ...)
        ParamsModel = create_model("ParamsModel", **attrs)
        logger.info(f"ParamsModel: {ParamsModel.model_json_schema()}")
        try:
            dependent_data = ParamsModel(**params["dependent_data"])
        except ValidationError as e:
            raise ValueError(f"Dependent data validation failed: {e}")
        res = assigner.assign(params["var_name"], dict(dependent_data))
        return res.model_dump()
    except Exception as e:
        raise ValueError(f"Assigner function execute fail, error: {e}")


def var_validate(protocol_name: str, vars: dict) -> dict:
    data = {"data": vars}
    # validate by aimd model
    # aimd_model = _load_tmp_aimd_model(protocol_name)
    # try:
    #     aimd_model.VarModel(**vars)
    # except ValidationError as exc:
    #     data["errors"] = exc.errors()

    # validate by model
    model = import_module(f"protocols.{protocol_name}.model")
    if model is not None and hasattr(model, "VarModel"):
        try:
            model.VarModel(**vars)
        except ValidationError as exc:
            data["errors"] = exc.errors()

    return data


def import_records(protocol_name: str, params: dict) -> dict:
    for k, v in params.get("env_vars", {}).items():
        if v is not None:
            os.environ[k] = str(v)

    protocol_path = os.path.abspath(f"./protocols/{protocol_name}")
    input_filename = params.get("input_filename")
    if not isinstance(input_filename, str) or input_filename == "":
        raise ValueError("input_filename is required")

    input_path = os.path.abspath(os.path.join(protocol_path, input_filename))
    if not input_path.startswith(f"{protocol_path}{os.sep}"):
        raise ValueError("input_filename must point inside the protocol package")
    if not os.path.isfile(input_path):
        raise ValueError("input file not found")

    result = import_airalogy_records(
        protocol_dir=protocol_path,
        input_path=input_path,
        input_format=params.get("input_format", "auto"),
        allow_extra_var_fields=bool(params.get("allow_extra_var_fields", False)),
        require_complete_quiz=bool(params.get("require_complete_quiz", False)),
        include_template_defaults=bool(params.get("include_template_defaults", True)),
        generate_record_ids=True,
        validate_model_sync=bool(params.get("validate_model_sync", True)),
        record_version=1,
    )

    return {
        "records": result.records,
        "errors": [
            {
                "row_number": error.row_number,
                "column": error.column,
                "message": error.message,
            }
            for error in result.errors
        ],
    }


def main(action: str, protocol_name: str, input_params: str):
    logger.info(
        f"action: {action}, protocol_name: {protocol_name}, input_params: {input_params}"
    )
    try:
        params = json.loads(input_params)

        if action == "get_protocol_info":
            result = get_protocol_info(protocol_name, params)
        elif action == "var_assign":
            result = var_assign(protocol_name, params)
        elif action == "var_validate":
            result = var_validate(protocol_name, params)
        elif action == "import_records":
            result = import_records(protocol_name, params)
        else:
            raise ValueError(f"Unknown action: {action}")

        result = {
            "success": True,
            "message": "",
            "data": result,
        }
        output = json.dumps(
            result, cls=RNJSONEncoder, separators=(",", ":"), ensure_ascii=False
        )
    except Exception as e:
        logger.exception(e)
        result = {"success": False, "message": str(e), "error_type": type(e).__name__}
        output = json.dumps(result, separators=(",", ":"), ensure_ascii=False)

    logger.info(f"output: {output}")
    # restore stdout
    sys.stdout = original_stdout
    print(output)


if __name__ == "__main__":
    action = sys.argv[1]
    reseach_node_name = sys.argv[2]
    params = sys.argv[3] if len(sys.argv) > 2 else "{}"
    main(action, reseach_node_name, params)
