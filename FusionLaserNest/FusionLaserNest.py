"""Ponto de entrada do add-in FusionLaserNest.

Fusion carrega este arquivo (mesmo nome da pasta e do .manifest) e chama
run(context) ao ativar o add-in e stop(context) ao desativar/fechar.
Toda a logica de fato mora em fusion_adapter/ui.py; este arquivo so registra
e remove os comandos da interface.
"""
import traceback

import adsk.core

from .fusion_adapter import ui


def run(context):
    app = None
    try:
        app = adsk.core.Application.get()
        ui.start_ui(app)
    except Exception:
        if app is not None:
            app.userInterface.messageBox(
                "Falha ao iniciar o FusionLaserNest:\n{}".format(traceback.format_exc())
            )


def stop(context):
    try:
        app = adsk.core.Application.get()
        ui.stop_ui(app)
    except Exception:
        app = adsk.core.Application.get()
        if app is not None:
            app.userInterface.messageBox(
                "Falha ao encerrar o FusionLaserNest:\n{}".format(traceback.format_exc())
            )
