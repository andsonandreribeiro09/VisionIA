import os
from importlib import import_module


APP_MODULES = {
    "medicao": "medicao_app",
    "laboratorio": "laboratorio_app",
    "admin": "admin_app",
}


module_name = os.getenv("VISIONAI_APP", "medicao").strip().lower()
module_path = APP_MODULES.get(module_name, module_name)

app = import_module(module_path).app


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
