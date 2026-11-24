"""Comando do Fusion (dialogo + eventos) e orquestracao de todo o fluxo:
selecionar faces -> nivelar -> nestar -> criar esbocos -> exportar -> relatorio.

Todo o trabalho de criacao/edicao de modelo acontece dentro do handler do
evento `execute`, garantindo uma unica transacao de undo. Qualquer excecao e
capturada, mostrada de forma curta em pt-BR e o traceback completo e gravado
em log.txt na pasta do add-in.
"""
from __future__ import annotations

import datetime
import os
import traceback
from typing import Dict, List

import adsk.core
import adsk.fusion

from ..core.geometry2d import PartShape, convex_hull, orientation_candidates, place_part_shape, polygon_area
from ..core.nesting import MaxRectsNester, PartForNesting
from ..core.report import build_report_text
from ..core.units import cm_to_mm
from . import exporter, selection, sketch_builder, test_parts
from .face_to_2d import FacePartData, extract_part_from_face

ADDIN_NAME = "FusionLaserNest"
CMD_ID_NEST = "FusionLaserNest_NestFacesCmd"
CMD_ID_TEST = "FusionLaserNest_CreateTestPartsCmd"

ADDINS_PANEL_ID = "SolidScriptsAddinsPanel"
DESIGN_WORKSPACE_ID = "FusionSolidEnvironment"
MODIFY_PANEL_ID = "SolidModifyPanel"

# Painel(is) onde os botoes sao adicionados, alem do Add-Ins: um comando que
# modifica/gera geometria a partir do design pertence, por convencao da
# propria Autodesk ("Command Icons" / "Positioning Your Controls", ver
# README), ao painel MODIFICAR da aba SOLIDO. Guardado como lista para o caso
# de itemById nao achar o painel (versao futura do Fusion renomear o ID) --
# nesse caso o codigo so pula, sem quebrar (ver _add_to_panel).
_TARGET_PANELS = [
    (None, ADDINS_PANEL_ID),  # None = ui.allToolbarPanels (independe de workspace)
    (DESIGN_WORKSPACE_ID, MODIFY_PANEL_ID),
]

ROTATION_MODES = [
    ("Nenhuma", "none"),
    ("0/90/180/270", "rect4"),
    ("Automatica", "auto"),
]

_handlers = []


def _addin_root_folder() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log_exception(exc: BaseException) -> None:
    log_path = os.path.join(_addin_root_folder(), "log.txt")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 70 + "\n")
            f.write(datetime.datetime.now().isoformat() + "\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


def _resource_folder(subfolder: str) -> str:
    return os.path.join(_addin_root_folder(), "resources", subfolder)


def _find_panel(ui: "adsk.core.UserInterface", workspace_id, panel_id: str):
    """Acha um painel de toolbar, opcionalmente escopado a um workspace.
    Retorna None (sem lancar excecao) se o workspace ou o painel nao existir
    -- por exemplo, se a Autodesk renomear o ID num Fusion futuro."""
    try:
        if workspace_id is None:
            return ui.allToolbarPanels.itemById(panel_id)
        workspace = ui.workspaces.itemById(workspace_id)
        if workspace is None:
            return None
        return workspace.toolbarPanels.itemById(panel_id)
    except Exception:
        return None


def start_ui(app: "adsk.core.Application") -> None:
    ui = app.userInterface
    cmd_defs = ui.commandDefinitions

    if cmd_defs.itemById(CMD_ID_NEST) is None:
        nest_def = cmd_defs.addButtonDefinition(
            CMD_ID_NEST,
            "Nest Faces (Laser)",
            "Nivela, encaixa (nesting) e exporta DXF/SVG das faces selecionadas para corte a laser.",
            _resource_folder("nest_command"),
        )
        handler = NestFacesCommandCreatedHandler()
        nest_def.commandCreated.add(handler)
        _handlers.append(handler)

    if cmd_defs.itemById(CMD_ID_TEST) is None:
        test_def = cmd_defs.addButtonDefinition(
            CMD_ID_TEST,
            "Criar pecas de teste (FusionLaserNest)",
            "Cria um documento novo com 4 pecas de teste para validar o nivelamento e o nesting.",
            _resource_folder("test_command"),
        )
        handler = TestPartsCommandCreatedHandler()
        test_def.commandCreated.add(handler)
        _handlers.append(handler)

    for workspace_id, panel_id in _TARGET_PANELS:
        panel = _find_panel(ui, workspace_id, panel_id)
        if panel is None:
            continue
        if panel.controls.itemById(CMD_ID_NEST) is None:
            panel.controls.addCommand(cmd_defs.itemById(CMD_ID_NEST))
        if panel.controls.itemById(CMD_ID_TEST) is None:
            panel.controls.addCommand(cmd_defs.itemById(CMD_ID_TEST))


def stop_ui(app: "adsk.core.Application") -> None:
    ui = app.userInterface

    for workspace_id, panel_id in _TARGET_PANELS:
        panel = _find_panel(ui, workspace_id, panel_id)
        if panel is None:
            continue
        for cmd_id in (CMD_ID_NEST, CMD_ID_TEST):
            control = panel.controls.itemById(cmd_id)
            if control is not None:
                control.deleteMe()

    for cmd_id in (CMD_ID_NEST, CMD_ID_TEST):
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if cmd_def is not None:
            cmd_def.deleteMe()

    _handlers.clear()


# ---------------------------------------------------------------------------
# Comando "Criar pecas de teste"
# ---------------------------------------------------------------------------


class TestPartsCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
            on_execute = TestPartsExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except Exception as exc:
            _log_exception(exc)
            ui.messageBox("Erro ao preparar o comando de pecas de teste. Veja log.txt.")


class TestPartsExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            test_parts.create_test_document(app)
        except Exception as exc:
            _log_exception(exc)
            ui.messageBox("Falha ao criar o documento de teste. Veja log.txt na pasta do add-in.")


# ---------------------------------------------------------------------------
# Comando "Nest Faces (Laser)"
# ---------------------------------------------------------------------------


class NestFacesCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            design = adsk.fusion.Design.cast(app.activeProduct)
            if design is None:
                ui.messageBox("Abra um documento de design do Fusion antes de rodar este comando.")
                return

            event_args = adsk.core.CommandCreatedEventArgs.cast(args)
            cmd = event_args.command
            inputs = cmd.commandInputs

            sel_input = inputs.addSelectionInput("faces", "Faces", "Selecione a face plana de maior area de cada peca")
            sel_input.addSelectionFilter("PlanarFaces")
            sel_input.setSelectionLimits(1, 0)

            inputs.addValueInput("sheetWidth", "Largura", "mm", adsk.core.ValueInput.createByString("600 mm"))
            inputs.addValueInput("sheetHeight", "Comprimento", "mm", adsk.core.ValueInput.createByString("400 mm"))
            inputs.addValueInput("spacing", "Espacamento", "mm", adsk.core.ValueInput.createByString("3 mm"))
            inputs.addValueInput("margin", "Margem", "mm", adsk.core.ValueInput.createByString("5 mm"))

            rot_input = inputs.addDropDownCommandInput("rotationMode", "Rotacao", adsk.core.DropDownStyles.TextListDropDownStyle)
            rot_input.tooltip = "Nenhuma: respeita o veio. 0/90/180/270: gira em passos de 90. Automatica: retangulo minimo (rotating calipers) + tentativa em +90."
            for i, (label, _mode) in enumerate(ROTATION_MODES):
                rot_input.listItems.add(label, i == 2)  # padrao: Automatica

            inputs.addIntegerSpinnerCommandInput("quantity", "Quantidade", 1, 9999, 1, 1)

            inputs.addStringValueInput("outputFolder", "Pasta", "")
            inputs.addBoolValueInput("browseFolder", "Escolher pasta...", False, "", False)

            create_input = inputs.addBoolValueInput("createSketches", "Criar esbocos", True, "", True)
            create_input.isFullWidth = True
            create_input.tooltip = "Mantem o componente/esbocos de nesting no design depois de terminar."

            export_input = inputs.addBoolValueInput("exportFiles", "Exportar DXF/SVG", True, "", True)
            export_input.isFullWidth = True

            replace_input = inputs.addBoolValueInput("replacePrevious", "Substituir execucao anterior", True, "", False)
            replace_input.isFullWidth = True
            replace_input.tooltip = "Apaga os esbocos/componente NEST_* de uma execucao anterior deste comando antes de criar os novos."

            on_execute = NestFacesExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)

            on_input_changed = NestFacesInputChangedHandler()
            cmd.inputChanged.add(on_input_changed)
            _handlers.append(on_input_changed)

            on_validate = NestFacesValidateInputsHandler()
            cmd.validateInputs.add(on_validate)
            _handlers.append(on_validate)

        except Exception as exc:
            _log_exception(exc)
            ui.messageBox("Erro ao montar o dialogo do comando. Veja log.txt.")


class NestFacesInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            event_args = adsk.core.InputChangedEventArgs.cast(args)
            changed = event_args.input
            if changed.id != "browseFolder":
                return

            inputs = event_args.firingEvent.sender.commandInputs
            folder_dialog = ui.createFolderDialog()
            folder_dialog.title = "Escolha a pasta de saida"
            result = folder_dialog.showDialog()
            if result == adsk.core.DialogResults.DialogOK:
                output_input = adsk.core.StringValueCommandInput.cast(inputs.itemById("outputFolder"))
                output_input.value = folder_dialog.folder
        except Exception as exc:
            _log_exception(exc)


class NestFacesValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            event_args = adsk.core.ValidateInputsEventArgs.cast(args)
            inputs = event_args.firingEvent.sender.commandInputs

            sel_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("faces"))
            if sel_input.selectionCount < 1:
                event_args.areInputsValid = False
                return

            width = inputs.itemById("sheetWidth").value
            height = inputs.itemById("sheetHeight").value
            spacing = inputs.itemById("spacing").value
            margin = inputs.itemById("margin").value
            if width <= 0 or height <= 0 or spacing < 0 or margin < 0:
                event_args.areInputsValid = False
                return

            export_files = adsk.core.BoolValueCommandInput.cast(inputs.itemById("exportFiles")).value
            output_folder = adsk.core.StringValueCommandInput.cast(inputs.itemById("outputFolder")).value
            if export_files and not output_folder.strip():
                event_args.areInputsValid = False
                return

            event_args.areInputsValid = True
        except Exception:
            # Nunca deixar o validateInputs quebrar o comando; so nao valida.
            pass


class NestFacesExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        nest_container = None

        try:
            design = adsk.fusion.Design.cast(app.activeProduct)
            event_args = adsk.core.CommandEventArgs.cast(args)
            inputs = event_args.command.commandInputs

            sel_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("faces"))
            sheet_width_mm = cm_to_mm(inputs.itemById("sheetWidth").value)
            sheet_height_mm = cm_to_mm(inputs.itemById("sheetHeight").value)
            spacing_mm = cm_to_mm(inputs.itemById("spacing").value)
            margin_mm = cm_to_mm(inputs.itemById("margin").value)
            quantity = adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById("quantity")).value
            output_folder = adsk.core.StringValueCommandInput.cast(inputs.itemById("outputFolder")).value
            create_sketches = adsk.core.BoolValueCommandInput.cast(inputs.itemById("createSketches")).value
            export_files = adsk.core.BoolValueCommandInput.cast(inputs.itemById("exportFiles")).value
            replace_previous = adsk.core.BoolValueCommandInput.cast(inputs.itemById("replacePrevious")).value

            rot_input = adsk.core.DropDownCommandInput.cast(inputs.itemById("rotationMode"))
            rotation_mode = ROTATION_MODES[rot_input.selectedItem.index][1]

            check = selection.collect_selected_faces(sel_input)
            if check.rejected_non_planar:
                ui.messageBox(
                    f"{check.rejected_non_planar} selecao(oes) nao-planar(es) foram ignoradas."
                )
            if check.duplicate_body_warning:
                names = ", ".join(check.duplicate_body_warning)
                ui.messageBox(
                    "Aviso: mais de uma face selecionada pertence ao mesmo corpo "
                    f"(provavel duplicata face superior/inferior): {names}\n"
                    "Continuando mesmo assim."
                )

            if not check.valid_faces:
                ui.messageBox("Nenhuma face plana valida foi selecionada.")
                return

            face_parts: Dict[str, FacePartData] = {}
            for i, face in enumerate(check.valid_faces):
                part_id = f"peca{i + 1:02d}_{face.body.name}"
                face_parts[part_id] = extract_part_from_face(face, part_id, quantity)

            parts_for_nesting: List[PartForNesting] = []
            instance_to_base: Dict[str, str] = {}
            shapes_by_instance: Dict[str, PartShape] = {}

            for part_id, fp in face_parts.items():
                hull = convex_hull(fp.part_shape.outer.approx_polygon)
                orientations = orientation_candidates(hull, rotation_mode)
                area = polygon_area(fp.part_shape.outer.approx_polygon)
                for k in range(quantity):
                    instance_id = f"{part_id}#{k + 1}"
                    instance_to_base[instance_id] = part_id
                    shapes_by_instance[instance_id] = fp.part_shape
                    parts_for_nesting.append(PartForNesting(part_id=instance_id, orientations=orientations, area=area))

            nester = MaxRectsNester()
            result = nester.pack(parts_for_nesting, sheet_width_mm, sheet_height_mm, spacing=spacing_mm, margin=margin_mm)

            need_component = create_sketches or export_files
            if need_component:
                if replace_previous:
                    sketch_builder.delete_previous_nest_artifacts(design)

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                nest_label = f"{sketch_builder.NEST_PREFIX}{timestamp}"
                nest_container = sketch_builder.create_nest_component(design, nest_label)

                if nest_container.is_fallback:
                    ui.messageBox(
                        "Este documento e do tipo 'Peca' (Part Design), que so permite um "
                        "componente. Os esbocos foram criados diretamente no componente raiz "
                        f"(nomes com prefixo '{nest_label}') em vez de um componente separado."
                    )

                placements_by_sheet: Dict[int, list] = {}
                for placement in result.placements:
                    placements_by_sheet.setdefault(placement.sheet_index, []).append(placement)

                if export_files and output_folder:
                    os.makedirs(output_folder, exist_ok=True)

                for sheet_index in sorted(placements_by_sheet.keys()):
                    sketch = sketch_builder.create_sheet_sketch(
                        nest_container.component, f"{nest_label}_Chapa_{sheet_index + 1}"
                    )
                    nest_container.register_sketch(sketch)
                    sketch_builder.draw_sheet_outline(sketch, sheet_width_mm, sheet_height_mm)

                    positioned_parts = []
                    for placement in placements_by_sheet[sheet_index]:
                        base_id = instance_to_base[placement.part_id]
                        fp = face_parts[base_id]
                        x_mm = placement.x + margin_mm
                        y_mm = placement.y + margin_mm

                        sketch_builder.place_and_draw_part(
                            sketch,
                            fp.exact_outer_curves,
                            fp.exact_hole_curves,
                            placement.orientation,
                            x_mm,
                            y_mm,
                        )

                        if export_files:
                            shape = shapes_by_instance[placement.part_id]
                            positioned_parts.append(place_part_shape(shape, placement.orientation, x_mm, y_mm, sheet_index))

                    if export_files and output_folder:
                        dxf_path, svg_path = exporter.sheet_filepaths(output_folder, "chapa", sheet_index)
                        exporter.export_dxf(design, sketch, dxf_path)
                        exporter.export_svg(sheet_width_mm, sheet_height_mm, positioned_parts, svg_path)

                if not create_sketches:
                    nest_container.cleanup()
                    nest_container = None

            total_parts = len(parts_for_nesting)
            report_text = build_report_text(result, total_parts)

            if export_files and output_folder:
                report_path = os.path.join(output_folder, "relatorio.txt")
                try:
                    with open(report_path, "w", encoding="utf-8") as f:
                        f.write(report_text)
                    report_text += f"\n\n(Relatorio tambem salvo em {report_path})"
                except OSError:
                    pass  # nao bloqueia o comando so por falha ao gravar o relatorio

            ui.messageBox(report_text)

        except Exception as exc:
            _log_exception(exc)
            if nest_container is not None:
                try:
                    nest_container.cleanup()
                except Exception:
                    pass
            ui.messageBox(
                "Ocorreu um erro ao nivelar/nestar/exportar as pecas. Detalhes em log.txt na pasta do add-in."
            )
