import os
from importlib import import_module


APP_MODULES = {
    "medicao": "medicao_app",
    "laboratorio": "laboratorio_app",
}


module_name = os.getenv("VISIONAI_APP", "medicao").strip().lower()
module_path = APP_MODULES.get(module_name, module_name)

app = import_module(module_path).app
