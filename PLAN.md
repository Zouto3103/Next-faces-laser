# PLAN.md — FusionLaserNest

## 1. Objetivo

Add-in Python para Fusion (Windows) que recebe faces planas selecionadas pelo usuário
(a maior face de cada corpo já dividido/espessurado), NIVELA cada uma no plano XY,
faz NESTING (encaixe) das peças dentro de uma ou mais chapas, gera esboços 2D num
componente novo (sem alterar o design original) e exporta DXF + SVG vetoriais por chapa.

Motivação registrada pelo usuário: o add-in "FuseNest 2D Nesting" não gira peças e
desperdiça chapa — este add-in implementa nesting com rotação (0/90/180/270 e modo
automático via retângulo mínimo/rotating calipers).

## 2. Pesquisa da API — o que foi confirmado e onde

Toda a pesquisa foi feita consultando a documentação oficial da API do Fusion
(help.autodesk.com/.../Fusion-360-API/) através do servidor de busca de documentação
da Autodesk (mesmo conteúdo do site, mesmas URLs `GUID-...`). Resumo por item pedido:

1. **Add-in Python / manifest / pasta AddIns (Windows)**
   - Estrutura confirmada: arquivo `<Nome>.py` (entry point com `run(context)` e
     `stop(context)`) + `<Nome>.manifest` (JSON) com o mesmo nome do arquivo .py e da
     pasta. Campos do manifest: `autodeskProduct`, `type: "addin"`, `author`,
     `description`, `supportedOS: "windows|mac"`, `editEnabled`.
   - Pasta de instalação no Windows:
     `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\<NomeDoAddIn>\`.
   - Fontes: "Using the Python Add-in Template"
     (help.autodesk.com/.../PythonTemplate_UM.htm) e "Creating a Script or Add-In".

2. **CommandInputs / ciclo de eventos**
   - `CommandInputs.addSelectionInput(id, name, tooltip) -> SelectionCommandInput`;
     `SelectionCommandInput.addSelectionFilter('PlanarFaces')`;
     `setSelectionLimits(minimum, maximum)`. Filtro `PlanarFaces` confirmado na lista
     oficial de Selection Filters.
   - `addValueInput(id, name, unitType, initialValue: ValueInput)`,
     `addBoolValueInput(id, name, isCheckBox, resourceFolder='', initialValue=False)`,
     `addDropDownCommandInput(id, name, dropDownStyle)`.
   - Ciclo: `ui.commandDefinitions.addButtonDefinition(...)` →
     `commandCreated` (monta o diálogo e conecta os outros handlers) →
     `inputChanged` (habilita/desabilita campos, nunca edita o modelo) →
     `validateInputs` (define `eventArgs.areInputsValid`) →
     `execute` (única transação/undo — todo o trabalho de nivelar, nestar, criar
     esboços e exportar acontece aqui).
   - Fonte: "Fusion Commands" (Events in the Fusion API / Command Inputs).

3. **BRepFace / Plane / loops / edges / CurveEvaluator3D**
   - `BRepFace.geometry` retorna `Plane` quando a face é planar; `Plane.normal`,
     `Plane.origin` (leitura/escrita), `Plane.uDirection`, `Plane.vDirection` (somente
     leitura).
   - `BRepFace.loops` (`BRepLoops`) → cada `BRepLoop.isOuter` indica se é o contorno
     externo (há exatamente 1 externo e 0+ internos = furos/dentes/encaixes).
   - `BRepLoop.edges` → `BRepEdge.geometry` retorna `Line3D | Arc3D | Circle3D |
     Ellipse3D | EllipticalArc3D | NurbsCurve3D` (todas derivam de `Curve3D` e têm
     `transformBy(matrix)`).
   - `BRepEdge.evaluator` → `CurveEvaluator3D.getStrokes(...)` usado apenas para
     discretizar (polilinha de aproximação) para cálculo do casco convexo/retângulo
     envolvente do nesting — nunca para a geometria exportada.
   - Fontes: "Fusion Models (B-Rep and Geometry)", `BRepLoop.isOuter`, `BRepEdge`,
     `Arc3D`/`Circle3D`/`Line3D`/`NurbsCurve3D` Object pages.

4. **Matrix3D — nivelamento sem espelhamento**
   - `Matrix3D.setToAlignCoordinateSystems(fromOrigin, fromX, fromY, fromZ, toOrigin,
     toX, toY, toZ) -> bool` mapeia um sistema de coordenadas "from" para um "to".
   - `Matrix3D.determinant` (double, somente leitura) — usado para *verificar* que a
     matriz é uma rotação pura (determinante ≈ +1), nunca uma reflexão.
   - **Decisão de projeto** (a documentação não garante que `uDirection × vDirection
     == normal` para todo `Plane`): construímos nós mesmos os eixos do sistema "from"
     como uma base ortonormal *à direita*, para garantir determinante +1 por
     construção, em vez de confiar cegamente em `uDirection`/`vDirection`:
     ```
     fromZ = plane.normal.normalized
     fromX = (plane.uDirection projetado no plano ⟂ fromZ).normalized
     fromY = fromZ × fromX          # right-handed, nunca espelha
     ```
     Isso resolve o requisito 4 (rotação própria, sem espelhar a peça).
   - `Curve3D.transformBy(matrix)` (herdado por Line3D/Arc3D/Circle3D/NurbsCurve3D)
     aplica a mesma matriz à geometria exata das arestas.

5. **Criação de curvas em esboço (plano XY de um novo componente)**
   - `sketch.sketchCurves.sketchLines.addByTwoPoints(p1, p2)`
   - `sketch.sketchCurves.sketchArcs.addByCenterStartSweep(center, startPoint, sweepAngleRad)`
     (arco sempre paralelo ao plano XY do esboço — é exatamente o nosso caso após
     nivelar a face)
   - `sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius)`
   - Splines / elipses: **decisão** — convertidas para `NurbsCurve3D` (via
     `Arc3D/Circle3D/Ellipse3D/EllipticalArc3D.asNurbsCurve` quando necessário, ou
     diretamente para `NurbsCurve3D`) e inseridas com
     `sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve(nurbsCurve)`. O método
     antigo `SketchFittedSplines.addByNurbsCurve` está **retirado** (setembro/2022);
     o substituto oficial é `SketchFixedSplines.addByNurbsCurve`, que preserva a
     geometria exata (não é uma curva "fit" aproximada).
   - Fontes: `SketchArcs`, `SketchFixedSplines.addByNurbsCurve`,
     `SketchFittedSplines.addByNurbsCurve` (retired).

6. **Unidades**
   - Motor interno do Fusion trabalha sempre em **centímetros** para comprimento
     (`UnitsManager` / valores de `Point3D`, `BRepEdge.length`, etc.).
   - UI do add-in pedida em **mm**: toda entrada numérica (`ValueCommandInput`) usa
     `unitType='mm'`; internamente convertida com
     `design.unitsManager.convert(valor, 'mm', 'cm')` antes de qualquer cálculo/API.
   - `ExportManager.createDXFSketchExportOptions(filename, sketch)` cria um
     `DXFSketchExportOptions` cuja propriedade `units` (string) controla a unidade de
     saída do arquivo DXF — setamos explicitamente para `'mm'` (não confiamos no
     default, que é a unidade do documento).
   - Fonte: `UnitsManager` Object, `DXFSketchExportOptions` Object.

7. **Esboço/componente novo sem alterar o design original**
   - `design.rootComponent.occurrences.addNewComponent(Matrix3D.create())` cria uma
     nova `Occurrence`/`Component` (`NEST_<timestamp>`) na raiz, sem tocar nos corpos
     originais. Cada chapa recebe um `Sketch` dentro desse componente
     (`newComp.sketches.add(newComp.xYConstructionPlane)`).
   - Todo o trabalho ocorre dentro do handler do evento `execute` do `Command`, então
     Fusion agrupa tudo numa única transação/undo (requisito: "operação deve poder
     ser desfeita em um único passo").
   - Fonte: "Documents, Products, Components, Occurrences, and Proxies",
     `Occurrences.addNewComponent`.

8. **Exportação DXF/SVG**
   - `ExportManager.createDXFSketchExportOptions(filename, sketch)` — **API em
     preview** desde janeiro/2025 (a própria documentação da Autodesk avisa: "you
     should never deliver any programs that use any preview capabilities" para
     distribuição comercial). Foi a substituta indicada pelo usuário para o método
     retirado `Sketch.saveAsDXF` (removido em jul/2025), então é a única forma atual
     de exportar DXF de um esboço via API. **Risco documentado no README.**
   - Propriedades usadas: `isConstructionExported = False`,
     `isPointsExported = False`, `isProjectedGeometryExported = False`,
     `units = 'mm'`. Isso evita exportar a geometria de construção (contorno da
     chapa) e pontos soltos no DXF.
   - `ExportManager.execute(options) -> bool`.
   - SVG: escrito manualmente (biblioteca padrão, `xml.etree.ElementTree` +
     strings), sem depender de nenhuma API do Fusion — os dados de entrada são os
     mesmos objetos geométricos puros (`core/geometry2d.py`) usados no nesting.

## 3. Arquitetura

```
FusionLaserNest/
  FusionLaserNest.py         # entry point (run/stop), registra o comando na UI
  FusionLaserNest.manifest
  core/                      # Python puro, testável com pytest fora do Fusion
    geometry2d.py            # Point2D, Polyline2D, PlacedPart, convex hull, rotating calipers
    nesting.py               # interface Nester + MaxRectsNester (plugável)
    svg_writer.py            # gera SVG a partir de PlacedSheet (sem tocar em adsk.*)
    report.py                # monta texto do relatório final
  fusion_adapter/            # única camada que importa adsk.*
    selection.py             # valida seleção de faces planas, detecta duplicata por corpo
    face_to_2d.py            # nivela a face (Matrix3D), extrai contornos exatos + polilinha p/ nesting
    sketch_builder.py        # cria componente NEST_*, esboços, reconstrói curvas exatas
    exporter.py              # DXF (ExportManager) e chama svg_writer
    ui.py                    # comando, CommandInputs, eventos, orquestração, try/except + log.txt
  tests/
    test_geometry2d.py
    test_nesting.py
    test_svg_writer.py
    test_units.py
  install.ps1
  README.md
  PLAN.md
```

### Fluxo de dados (`ui.py` → `execute` event)

1. `selection.py`: lê as `BRepFace` do `SelectionCommandInput`, rejeita não-planas
   (já filtradas pela UI, mas revalidado por segurança), avisa (mensagem, não
   bloqueia) se duas faces vierem do mesmo `BRepBody`.
2. `face_to_2d.py`, por face:
   - monta a matriz de nivelamento (right-handed, ver item 4 acima) e confere
     `abs(matrix.determinant - 1.0) < 1e-6`;
   - percorre `BRepLoops`; para cada loop, percorre `BRepEdges`, aplica
     `geometry.copy().transformBy(matrix)` e guarda a lista de curvas exatas
     (tipo + parâmetros) **e** uma polilinha (`CurveEvaluator3D.getStrokes`,
     tolerância configurável) só para cálculo geométrico 2D;
   - resultado: um `PartLoops` (Python puro: contorno externo + furos, cada um como
     lista de segmentos exatos + polígono aproximado) por face selecionada.
3. `core/geometry2d.py` (puro): calcula casco convexo do contorno externo
   aproximado, aplica rotating calipers para achar o retângulo de área mínima,
   gera as variantes de rotação pedidas pelo usuário (nenhuma / 0-90-180-270 /
   automática + também tenta +90° sobre o ângulo ótimo).
4. `core/nesting.py`: interface `Nester.pack(parts, sheet) -> PackResult` — v1
   implementa `MaxRectsNester` (Maximal Rectangles, heurística best-area-fit),
   ordenando peças por área decrescente; abre chapas adicionais deslocadas em X
   quando não cabe mais nada na atual; retorna também a lista de não alocadas
   (peça maior que a chapa em qualquer rotação permitida).
5. `sketch_builder.py`: cria `NEST_<timestamp>` (novo componente na raiz), um
   `Sketch` por chapa; para cada peça alocada, aplica a transformação 2D
   (translação + rotação escolhida pelo nesting) às curvas **exatas** guardadas no
   passo 2 e recria cada curva no esboço (linha/arco/círculo/NURBS); desenha o
   contorno da chapa como geometria de construção (não exportada).
6. `exporter.py`: para cada esboço de chapa, `ExportManager.createDXFSketchExportOptions`
   (unidades mm, sem construção/pontos) + escreve o SVG correspondente via
   `core/svg_writer.py` a partir dos mesmos dados 2D já transformados.
7. `report.py` monta o texto (peças alocadas/não alocadas, nº de chapas,
   aproveitamento % por chapa) mostrado em `ui.messageBox`.

Tudo dentro de um único `try/except` no handler de `execute`; qualquer exceção:
mensagem curta em pt-BR via `ui.messageBox` + traceback completo em
`log.txt` (pasta do add-in) + rollback (não deixamos esboço/componente pela metade —
se falhar após criar o componente `NEST_*`, ele é apagado antes de propagar o erro
visível ao usuário; como tudo roda dentro do `execute`, o Fusion também garante que
um "Cancel"/exceção não cria uma entrada não-undo-ável).

### Por que MaxRects (v1) e não polygon-nesting

Pedido explicitamente como v1; a interface `Nester` (um método `pack`) isola o
algoritmo de retângulos do resto do sistema para permitir trocar por nesting
poligonal depois sem tocar em `sketch_builder.py`/`exporter.py`.

## 4. Riscos e decisões registradas (ver também README §Decisões)

- **API em preview** (`createDXFSketchExportOptions`): pode mudar de assinatura em
  versões futuras do Fusion sem aviso prévio de compatibilidade. Mitigação: toda a
  chamada fica isolada em `exporter.py::export_dxf`, com try/except específico que
  gera mensagem clara caso a API mude.
- **`uDirection`/`vDirection` vs `normal`**: construímos a base nós mesmos (item 4)
  em vez de assumir que já formam uma base ortonormal à direita.
- **Arcos sempre CCW em Fusion** (`SketchArcs` sempre cria arco anti-horário mesmo
  com sweep negativo): ao reconstruir a partir de `Arc3D.getData` (startAngle/
  endAngle medidos com regra da mão direita ao redor da normal), calculamos
  `sweep = (endAngle - startAngle) mod 2π` e usamos sempre sweep positivo com
  `addByCenterStartSweep`, então a direção sai correta mesmo com a peculiaridade da
  API.
- **Elipses**: convertidas para NURBS (`asNurbsCurve`) e inseridas com
  `SketchFixedSplines.addByNurbsCurve` — não há um caso de teste dedicado no
  auto-teste do Fusion (fora de escopo pedido: só retângulo/furo, dentes, círculo,
  outro plano), mas o caminho de código é o mesmo dos splines.
- **Kerf, gravação, nesting poligonal, macOS**: fora de escopo (conforme pedido).

## 5. Plano de testes

- `tests/test_geometry2d.py`: casco convexo, rotating calipers (retângulo mínimo),
  rotação 90° necessária para caber, peça maior que a chapa → não alocada, teste de
  propriedade com retângulos aleatórios (seeds fixas), overlap/margem.
- `tests/test_svg_writer.py`: XML válido (`xml.etree.ElementTree.fromstring`),
  paths fechados, viewBox em mm, furos dentro do contorno externo.
- `tests/test_units.py`: quadrado de 100 mm → 100 mm no SVG (cm→mm).
- `tests/test_nesting.py`: MaxRects com múltiplas chapas, relatório de aproveitamento.
- Dependência de dev: `ezdxf` só em `tests/` (validação opcional de DXF), nunca
  importada pelo add-in em si.
- Dentro do Fusion: comando extra "Criar peças de teste" (checklist manual no
  README).
