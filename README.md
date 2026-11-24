# FusionLaserNest

Add-in Python para o Autodesk Fusion (Windows) que prepara peças de corpos
divididos para corte a laser: você seleciona as faces planas de maior área de
cada corpo, o add-in **nivela** cada uma no plano XY, faz o **nesting**
(encaixe, com rotação) dentro de uma chapa, cria **esboços 2D** num componente
novo (sem alterar o design original) e **exporta DXF e SVG** vetoriais por
chapa, prontos para LightBurn/RDWorks.

Feito porque o add-in "FuseNest 2D Nesting" não gira as peças e desperdiça
chapa.

## Instalação

Pré-requisitos: Windows, Fusion instalado, PowerShell.

```powershell
.\install.ps1
```

O script copia a pasta `FusionLaserNest\` para
`%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FusionLaserNest`
(local documentado pela Autodesk para add-ins instalados manualmente — ver
[Using the Python Add-in Template](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PythonTemplate_UM.htm)).
Ele remove qualquer instalação anterior e a pasta `tests/` antes de copiar (o
Fusion não precisa dos testes).

Depois de rodar o script:

1. Abra o Fusion.
2. Menu **UTILITIES > Add-Ins** (Scripts and Add-Ins).
3. Aba **Add-Ins**, selecione **FusionLaserNest**, clique **Run** (marque
   *Run on Startup* se quiser que carregue sempre).
4. Dois botões novos (com ícone próprio) aparecem em dois lugares do ambiente
   Design, aba **SÓLIDO**: no painel **MODIFICAR** (local natural para um
   comando que gera/edita geometria a partir do design, conforme a própria
   Autodesk recomenda — ver "User-Interface Customization" na seção de
   Pesquisa da API abaixo) e também no painel **ADD-INS**: **Nest Faces
   (Laser)** e **Criar peças de teste (FusionLaserNest)**.

Para atualizar depois de editar o código, rode `.\install.ps1` de novo.

## Uso

1. No seu design (com os corpos já divididos e com a espessura correta), rode
   **Nest Faces (Laser)**.
2. Selecione a face plana de maior área de cada peça (uma por corpo).
3. Preencha o diálogo:
   - **Largura/Comprimento** da chapa (mm, padrão 600 × 400).
   - **Espaçamento** entre peças (mm, padrão 3) e **Margem** da borda (mm,
     padrão 5).
   - **Rotação**: Nenhuma (respeita veio) / 0-90-180-270 / Automática
     (retângulo mínimo, com tentativa extra de +90°) — passe o mouse sobre o
     campo para ver a explicação de cada opção (tooltip).
   - **Quantidade** por peça (aplicada a todas as faces selecionadas).
   - **Pasta** de saída (botão "Escolher pasta...").
   - Checkboxes **Criar esboços no design**, **Exportar DXF/SVG** e
     **Substituir esboços de execuções anteriores** (apaga o componente/
     esboços `NEST_*` de uma rodada anterior antes de criar os novos — ligue
     se você está iterando no design e não quer ficar apagando à mão a cada
     rodada; desligue se quiser manter o histórico de execuções anteriores no
     documento).
4. Clique OK. Um relatório aparece com peças alocadas/não alocadas (com
   **ATENÇÃO** destacado se alguma peça não coube — verifique se a chapa é
   grande o bastante ou reduza a quantidade), número de chapas e
   aproveitamento (%) por chapa. Se "Exportar DXF/SVG" estiver marcado, esse
   mesmo relatório também é salvo como `relatorio.txt` na pasta de saída (não
   depende só de você ter visto a mensagem na hora).
5. Se "Criar esboços" estiver marcado, um componente `NEST_<data-hora>` fica no
   design (undo em um único passo). Se estiver desmarcado mas "Exportar" ligado,
   o componente é criado só temporariamente para gerar os arquivos e depois
   apagado.

Para testar sem ter um modelo próprio à mão, use **Criar peças de teste**: ele
abre um documento novo com 4 peças (ver checklist no fim deste README).

## Estrutura do projeto

```
FusionLaserNest/
  FusionLaserNest.py / .manifest   # entry point do add-in
  core/            # Python puro (sem adsk.*), testado com pytest
    geometry2d.py  # pontos, contornos, casco convexo, retangulo minimo, orientacoes
    nesting.py     # MaxRects (Best-Area-Fit), interface Nester plugavel
    svg_writer.py  # gera o SVG (mm, sem libs externas)
    units.py       # conversao cm <-> mm
    report.py      # texto do relatorio final
  fusion_adapter/  # unica camada que importa adsk.*
    selection.py     # valida faces selecionadas
    face_to_2d.py    # nivelamento (Matrix3D) + extracao de geometria exata
    sketch_builder.py# cria componente NEST_*, esbocos, reconstroi curvas
    exporter.py      # DXF (ExportManager) + SVG
    test_parts.py    # comando "Criar pecas de teste"
    ui.py            # dialogo, eventos, orquestracao, log de erros
  tests/           # pytest, roda fora do Fusion
install.ps1
PLAN.md
README.md
```

## Rodando os testes automatizados

```bash
pip install -r requirements-dev.txt
pytest FusionLaserNest/tests -q
```

Cobertura atual: 25 testes, todos passando — casco convexo, retângulo mínimo
(rotating calipers), caso que só resolve girando 90°, peça maior que a chapa
→ não alocada sem exceção, ausência de sobreposição respeitando espaçamento e
margem, teste de propriedade com retângulos aleatórios (sementes fixas), SVG
válido (XML bem formado via `xml.etree.ElementTree`), paths sempre fechados
(`M ... Z`), furo dentro do contorno externo, e conversão cm→mm (quadrado de
100 mm sai como 100 mm no SVG). `ezdxf` está listado como dependência de dev
opcional, mas não é usada: o add-in nunca escreve DXF por conta própria — ele
sempre delega ao `ExportManager` do Fusion, então não há DXF "nosso" para
validar fora do Fusion.

## Pesquisa da API (confirmada na documentação oficial)

Cada item abaixo foi confirmado consultando a documentação oficial do Fusion
(`help.autodesk.com/.../Fusion-360-API/`) antes de escrever qualquer código,
como pedido. Links:

1. **Versão do Python / estrutura do add-in / pasta AddIns (Windows)**
   [Using the Python Add-in Template](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PythonTemplate_UM.htm) —
   pasta `<Nome>/` com `<Nome>.py` + `<Nome>.manifest`; Windows:
   `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\<Nome>`.

2. **CommandInputs e ciclo de eventos**
   [SelectionCommandInput Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-568db63a-0f28-4307-9e02-e29f54820db1)
   (filtro `PlanarFaces` confirmado na lista de valores válidos), [CommandInputs Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-504c1dbc-5132-454e-86fd-72101fa55d84)
   (`addValueInput`, `addBoolValueInput`, `addDropDownCommandInput`,
   `addIntegerSpinnerCommandInput`, `addStringValueInput`, `addSelectionInput`),
   [Fusion Commands / Events](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-3922697A-7BF1-4799-9A5B-C8539DF57051)
   (ciclo `commandCreated` → `inputChanged` → `validateInputs` → `execute`, e
   por que tudo que edita o modelo deve ficar em `execute`, para virar uma
   única transação de undo).

3. **BRepFace / Plane / loops / edges / CurveEvaluator3D**
   [Fusion Models (B-Rep and Geometry)](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-1C3FFADB-52C4-49BB-8981-4A448FFE4442),
   [BRepLoop.isOuter](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-d5baa3b6-2977-4933-b8cd-9ec15458037a),
   [BRepEdge Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-f6ab0f2f-b27e-473a-9b91-cf6b9c99e218),
   [Plane Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-19c651ca-e796-4b2d-a183-505a1268f1b5)
   (`normal`, `origin`, `uDirection`, `vDirection`),
   [CurveEvaluator3D.getStrokes](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-3010a4a5-4b94-4a90-9efc-c2eec8541e39) e
   [getParameterExtents](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-27c2b508-abdc-4fa8-a3f5-4e154a43e7b4).

4. **Matrix3D — nivelamento sem espelhar**
   [Matrix3D Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-b831d9f4-c231-4b9f-9b4d-658614ecdc79)
   (`setToAlignCoordinateSystems`, `transformBy`, `determinant`),
   [Matrix3D.setToRotation](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-d2e83d0b-781c-4faf-91ff-6cd31cc2174d).

5. **Curvas de esboço**
   [SketchArcs Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-3e13ae2f-809a-4431-bd5f-3df4c12ce333) /
   [addByCenterStartSweep](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-2ff49f08-cd13-4602-9ab3-d86e10ce4fd0),
   [SketchFixedSplines.addByNurbsCurve](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-EA5FBD51-ED6F-4D04-83B2-D72A384BC6DA)
   (substituto do método **retirado** `SketchFittedSplines.addByNurbsCurve`,
   [confirmado como retirado em set/2022](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-EAC7918A-A198-499D-A649-1547FF35FF92)),
   [Arc3D](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-43846581-56f8-437d-8fb8-46c7183d2cbe),
   [Line3D](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-42613b0c-dd36-499f-8076-320856063f92),
   [Circle3D](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-42aa5c12-6bc6-46bb-ad15-7de61f625ae3),
   [NurbsCurve3D](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-de6fb48b-371f-49b6-80be-0ef62745404e).

6. **Unidades**
   [UnitsManager Object](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-9c2d17c1-70c6-4c2d-ae9e-c6f6f283b1a9)
   (internamente tudo em cm) e
   [DXFSketchExportOptions.units](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-CB435EE8-3475-4C72-831E-26024EFAB76F)
   e [DistanceUnits Enumerator](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-cb53a403-d687-4016-aae6-b03f095bdb61)
   (a propriedade `units` é do tipo `DistanceUnits`, um enum — **não** uma
   string; setamos `adsk.fusion.DistanceUnits.MillimeterDistanceUnits`
   explicitamente no DXF exportado. Descoberto em teste real: passar a string
   `'mm'` lança `TypeError`, já que a doc não deixa o tipo óbvio a partir só da
   descrição textual).

7. **Componente novo sem alterar o design**
   [Documents, Products, Components, Occurrences and Proxies](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-88A4DB43-CFDD-4CFF-B124-7EE67915A07A),
   [Occurrences.addNewComponent](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-8c7da023-bfd1-4816-9a57-a90dfcf3acd4).

8. **Exportação**
   [ExportManager.createDXFSketchExportOptions](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-0551C757-9019-4ECD-9E3B-5D15FEF7F077) e
   [ExportManager.execute](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-556625f1-e07a-480a-86d9-cf1140b073c8).
   O método antigo `Sketch.saveAsDXF` foi retirado (jul/2025, conforme
   observado pelo usuário) — `createDXFSketchExportOptions` é a substituta
   oficial indicada pela própria Autodesk, mas **é uma API em preview** (ver
   seção Riscos abaixo).

9. **Ícone do comando e onde colocar o botão**
   [User-Interface Customization](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-F31C76F0-8C74-4343-904C-68FDA9BB8B4C)
   — confirma a convenção de pastas de ícone (`16x16`/`32x32`/`64x64`,
   PNG ou SVG — usamos SVG, formato "preferred" segundo a doc) e recomenda
   textualmente: *"if a command modifies an existing model, it should
   probably be added to the MODIFY panel in the Design workspace"* — por
   isso o botão foi para o painel **MODIFICAR** (`SolidModifyPanel`) da aba
   SÓLIDO, além do painel ADD-INS (`SolidScriptsAddinsPanel`) de sempre.
   O ID exato do painel Modificar não veio confirmado literalmente na busca
   da documentação (só o padrão de nomenclatura `Solid<Nome>Panel`, visto em
   `SolidCreatePanel` num exemplo oficial), então o código busca o painel com
   `itemById` e simplesmente pula (sem travar) se o Fusion não o encontrar —
   ver `fusion_adapter/ui.py::_find_panel`.

## Decisões de projeto (onde a documentação não resolvia sozinha)

- **Base ortonormal própria no nivelamento**: a documentação não garante que
  `plane.uDirection × plane.vDirection == plane.normal` para todo `Plane`.
  Construímos a base "from" nós mesmos (`fromZ = normal`, `fromX = uDirection`
  projetado ⟂ normal, `fromY = fromZ × fromX`) e conferimos
  `abs(matrix.determinant - 1.0) < 1e-6` antes de aceitar a transformação —
  se der espelhamento, a operação aborta com um erro claro em vez de inverter
  a peça silenciosamente. Ver `fusion_adapter/face_to_2d.py::build_leveling_matrix`.

- **Direção do arco ao reconstruir**: `Arc3D.startAngle/endAngle` são medidos
  em torno da normal **própria** da curva (que pode ter ficado invertida pelo
  nivelamento, já que a geometria de uma aresta é independente da orientação
  da face). Por isso, ao recriar o arco com `addByCenterStartSweep`,
  calculamos o ângulo de varredura **geometricamente** a partir de
  `center`/`startPoint`/`endPoint` (que são posições, não dependem de normal) e
  só usamos a magnitude original para decidir o sinal do sweep — evita
  reconstruir o arco espelhado/complementar. Ver `sketch_builder.py::_draw_arc`.

- **`Arc3D.getData()` mede os ângulos a partir do `referenceVector` da curva,
  não do eixo +X global (bug real encontrado ao testar peça com raio)**: uma
  peça real com filetes exportou com um "buraco" de alguns mm exatamente nos
  cantos arredondados — o arco do filete aparecia rotacionado em torno do
  próprio centro, desconectado das linhas vizinhas. A causa:
  `Arc3D.getData()` retorna `startAngle`/`endAngle` "measured from the
  reference vector using the right hand rule around the normal vector" — e
  esse `referenceVector` é uma direção arbitrária interna da curva, quase
  nunca alinhada com o eixo +X. `fusion_adapter/face_to_2d.py::
  _arc_segment_from_arc3d` tratava esse ângulo como se já estivesse em
  relação a +X, rotacionando o `ArcSeg` reconstruído (usado no SVG e no
  cálculo do polígono para nesting) para a posição errada. **Importante**:
  isso não afetava o esboço criado no Fusion nem o DXF — `sketch_builder.py::
  _draw_arc` sempre usou `arc.center`/`arc.startPoint`/`arc.endPoint`
  (propriedades que o próprio Fusion já calcula certo) em vez de recalcular
  pontos a partir dos ângulos brutos, então só a exportação SVG (e a
  qualidade do polígono de nesting para peças com filetes) era afetada. A
  correção usa `arc.startPoint` (confiável) via `atan2` para achar o ângulo
  em relação a +X global, reaproveitando só a **magnitude** do sweep de
  `getData()` (essa sim independente de qualquer referência). O comando
  "Criar peças de teste" agora arredonda os 4 cantos da peça 1 (fillet, raio
  8 mm) — antes, nenhuma das 4 peças de teste tinha um arco parcial (só
  linhas e círculos inteiros), por isso essa classe de bug não tinha sido
  pega antes.
  - **Segundo bug, mais sutil (a "magnitude independe da referência" também
    era falsa)**: mesmo com a correção acima, uma peça real com fillet de 90°
    continuou exportando com um buraco. Comparando o SVG com o **DXF exportado
    no mesmo lote** (o DXF vem direto do esboço do Fusion e provou estar
    perfeito — confirma que `sketch_builder.py` nunca teve esse bug),
    reconstruí as coordenadas exatas à mão: o fillet real vai de (5,15) a
    (15,5) em torno do centro (15,15), um arco de 90°. Mas
    `sweep = (end_angle - start_angle) % 2π` a partir dos ângulos crus de
    `getData()` estava calculando **270°** — o arco **complementar** — não os
    90° corretos. Ou seja, nem a diferença entre os dois ângulos crus é
    confiável, só porque os dois vêm "na mesma referência" não significa que
    a subtração dê a magnitude física certa (motivo exato não fica claro pela
    documentação). **Correção definitiva**: parar de usar qualquer ângulo de
    `getData()`. Em vez disso, desambiguar geometricamente com um ponto real
    do **meio do arco**, obtido via
    [`CurveEvaluator3D.getPointAtParameter`](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-afeac4c2-5ea1-4d57-ac47-282a7fcd4de1)
    no parâmetro médio (`getParameterExtents` dá o intervalo): dos dois arcos
    possíveis entre `startPoint` e `endPoint` ao redor do mesmo centro (um de
    `delta_ccw` graus, outro de `360 - delta_ccw`), o ponto do meio real só
    pode estar em UM deles — isso resolve sem depender de nenhuma convenção
    interna do Fusion. Validado à mão contra os dados reais do DXF (ver
    `fusion_adapter/face_to_2d.py::_arc_segment_from_arc3d`, robusto também a
    qual ponto o Fusion rotula como "start").
  - **Terceiro bug (esse já no lado do SVG, não mais na extração)**: com os
    dois bugs acima corrigidos, o arco passou a **conectar** certinho com as
    linhas vizinhas (confirmado ponto a ponto contra o DXF), mas ainda assim
    curvava para o **lado errado** — o filete saía "para dentro" em vez de
    "para fora". Causa: `core/svg_writer.py` fixava `sweep-flag=1` no comando
    SVG `"A"` sempre, baseado num raciocínio sobre como a inversão do eixo Y
    (necessária porque nossa geometria usa Y para cima e o SVG usa Y para
    baixo) afeta a quiralidade do arco (CCW vira CW?) — esse raciocínio
    abstrato se provou errado. **Correção**: parar de *supor* a direção e
    **medir**: `_arc_svg_flags` calcula o ângulo de início/fim direto nas
    coordenadas já no espaço do SVG, compara com a magnitude verdadeira do
    arco (`seg.sweep`, já validada pela correção anterior) e escolhe o par de
    flags (`large-arc`, `sweep`) que bate exatamente com essa magnitude —
    sem depender de acertar nenhuma teoria sobre quiralidade. Validado com 2
    métodos independentes (incluindo a regra documentada do SVG "sweep=0 é
    sempre CCW visualmente") e travado com os dados reais dos 2 filetes do
    arquivo que o usuário mandou (`test_svg_arc_matches_real_fillet_from_
    reported_bug` em `test_svg_writer.py`).

- **Extração de arestas de um `BRepLoop` (três tentativas até acertar)**: um
  teste com uma peça real (painel com dentes de encaixe) exportou em
  ziguezague — segmentos ligados na ordem errada. Histórico completo, porque
  as duas primeiras tentativas pareciam corretas pela documentação mas não
  resolveram de verdade:
  1. **`loop.edges`** (tentativa original): não é documentado como
     ordenado, e na prática não vinha em ordem conectada → ziguezague.
  2. **Reconstruir a cadeia geometricamente**, encaixando segmentos por
     distância entre extremidades (`core/geometry2d.py::
     order_segments_into_chain`, ainda no código). Resolveu peças simples,
     mas em peças com muitas arestas bem próximas (dentes de encaixe
     apertados) a escolha "mais próxima" pode ser ambígua → sobravam arcos
     soltos no fim do contorno.
  3. **`loop.coEdges`** (percorrida via
     [`BRepCoEdge.next`](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-66ba0572-6be3-4ceb-8544-113d1e611ef5),
     documentada como "ordered head-to-tail") combinada com
     [`BRepCoEdge.isOpposedToEdge`](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-990a5416-7af6-49b7-93b3-5f12a7e8d5e5).
     Parecia a fonte "autoritativa" certa, mas em teste real com peças com
     **raio** continuou faltando arestas no contorno exportado — ou seja, o
     problema nunca foi só ordem/direção: a travessia via `.next` não estava
     visitando todas as co-edges do loop (a documentação não deixa claro por
     quê; pode repetir alguma e pular outra).
  - **Correção que resolve pela raiz**: em vez de continuar perseguindo qual
    fonte dá a "ordem certa", eliminamos a dependência de ordem por completo.
    `core/svg_writer.py` desenha **cada segmento como um sub-path SVG
    independente** (`M` próprio por segmento, todos concatenados no mesmo
    atributo `d` — o SVG aceita vários `M`); como cada segmento já tem
    coordenadas absolutas corretas e as extremidades compartilhadas coincidem
    exatamente (topologia B-Rep válida), a forma final fica certa **sem
    nenhuma dependência de ordem**. Isso deixou claro que só faltava garantir
    que **nenhuma aresta fica de fora** — e para isso `loop.edges` (voltamos
    a ele) é exatamente o que a documentação promete: "Returns the BRepEdges
    used by this loop", um conjunto **completo**, mesmo sem prometer ordem.
    `order_segments_into_chain` continua sendo aplicado sobre esse conjunto
    completo só por qualidade (deixa o polígono aproximado, usado no
    nesting, com pontos em sequência ao redor do contorno) — nunca descarta
    nada, é só uma permutação/inversão do que já foi extraído, então não tem
    como reintroduzir o bug de arestas faltando. Ver
    `fusion_adapter/face_to_2d.py::_extract_loop`.
  - A reconstrução do esboço no Fusion (`sketch_builder.py`) nunca foi afetada
    por nenhuma dessas variações do bug — cada curva é criada com coordenadas
    absolutas, direto dos objetos `Curve3D` reais, independente de ordem;
    só o polígono aproximado e o SVG exportado dependiam da cadeia estar
    correta. Cobertura: `test_order_segments_into_chain_*` e
    `test_is_chain_connected_*` em `test_geometry2d.py`, e
    `test_svg_path_is_correct_even_with_segments_scrambled_and_reversed` +
    `test_svg_arc_shape_independent_of_reversed_flag` em `test_svg_writer.py`.

- **Elipses e curvas exóticas → NURBS**: `Ellipse3D`/`EllipticalArc3D` (e
  qualquer curva que não seja linha/arco/círculo) são convertidas com
  `.asNurbsCurve()` e inseridas com `SketchFixedSplines.addByNurbsCurve`,
  preservando a forma exata. Para o cálculo de nesting (só a aproximação
  poligonal), usamos `CurveEvaluator3D.getStrokes` com tolerância de 0,05 mm.

- **Quantidade por peça é global**: o campo "Quantidade" do diálogo se aplica
  a **todas** as faces selecionadas igualmente (não há um campo por peça). Se
  quantidades diferentes por peça forem necessárias no futuro, o lugar natural
  é trocar esse spinner por um `TableCommandInput`.

- **Checkbox "Criar esboços" vs "Exportar"**: se **Exportar** estiver marcado
  mas **Criar esboços** desmarcado, o componente `NEST_*` ainda é criado
  internamente (o `ExportManager` precisa de um `Sketch` real para exportar) e
  é apagado logo depois de gerar os arquivos — assim o design fica limpo mas a
  exportação funciona.

- **Documentos do tipo "Peça" (Part Design) só aceitam 1 componente**: isso só
  apareceu ao testar de verdade no Fusion (não é algo a documentação avisa de
  forma óbvia). `Occurrences.addNewComponent` falha nesses documentos com
  `RuntimeError: "Os documentos de projeto de peça só podem conter um
  componente."`. A saída óbvia — criar um **documento novo** para os esboços —
  também não é permitida: a documentação do
  [`Documents.add`](https://help.autodesk.com/view/NINVFUS/ENU/?guid=GUID-2314d09a-c595-4f9a-ab8b-3e302dc5d860)
  avisa explicitamente que "Creating a document is not supported within any of
  the Command related events" (e o `execute` é um evento de comando). Por
  isso, quando `addNewComponent` falha, o add-in cai para criar os esboços
  **direto no componente raiz** do documento atual (nomes com prefixo
  `NEST_<data-hora>_...` para ficarem identificáveis e fáceis de apagar à
  mão), avisando o usuário com uma mensagem clara. Nesse caso o "undo em um
  passo só" continua valendo (os esboços são apagados juntos no
  `NestContainer.cleanup()` se o usuário desmarcar "Criar esboços" ou se der
  erro), mas o histórico de undo terá uma entrada por esboço criado em vez de
  uma entrada só, já que não há um componente-contêiner para agrupar tudo.
  Ver `fusion_adapter/sketch_builder.py::NestContainer`.

- **Peça maior que a chapa**: o `MaxRectsNester` tenta cada peça numa chapa
  totalmente vazia; se não couber em **nenhuma** orientação permitida nem
  numa chapa vazia, ela vai para a lista de não-alocadas e o algoritmo segue
  para a próxima peça (nunca trava nem lança exceção).

- **Espaçamento reservado mesmo na borda da última peça de uma fileira**: o
  algoritmo infla cada peça por `spacing` ao decidir onde encaixar (técnica
  padrão de MaxRects), então o espaçamento mínimo entre peças é sempre
  respeitado, mas pode sobrar um pouco de espaço não aproveitado perto das
  bordas do bin — aceitável para a v1.

- **Nesting: várias tentativas, não uma busca exaustiva**: `MaxRects` puro é
  um único passe guloso e a ordem em que as peças são inseridas muda bastante
  o resultado (a primeira peça "trava" o layout inicial da chapa). Em vez de
  só ordenar por área decrescente (única estratégia da v1 inicial),
  `MaxRectsNester.pack` agora roda o mesmo algoritmo **6 vezes**, cada vez
  ordenando as peças por um critério diferente (área, maior lado, perímetro,
  largura, altura, menor lado — todos decrescentes), e fica com o resultado
  que aloca mais peças, depois usa menos chapas, depois tem o maior
  aproveitamento médio (`MaxRectsNester._score`). Isso é uma melhoria real e
  mensurável — não é 100% ótimo (isso é NP-difícil; um metaheurístico como
  recozimento simulado chegaria mais perto, mas é bem mais código e mais
  lento) — mas responde à expectativa de que o add-in realmente "processe" em
  busca de um resultado melhor em vez de aceitar a primeira disposição que
  encontrar. Coberto por
  `test_multi_strategy_search_beats_single_area_only_pass` (caso real onde a
  estratégia antiga usava 6 chapas e a nova usa 5) e
  `test_pack_result_is_never_worse_than_any_single_strategy` em
  `test_nesting.py`.

## Limitações conhecidas / fora de escopo

- Compensação de kerf (fica no software do laser), gravação de
  texto/marcações, nesting **poligonal** (só retângulo envolvente na v1, mas
  a interface `Nester` em `core/nesting.py` é plugável para isso depois) e
  macOS: **fora de escopo**, conforme pedido.
- **`ExportManager.createDXFSketchExportOptions` é uma API em preview** da
  Autodesk (introduzida em jan/2025). A própria documentação avisa para não
  distribuir comercialmente um add-in que dependa de uma API em preview, já
  que a assinatura pode mudar sem aviso numa atualização futura do Fusion.
  Isso é inevitável aqui: é a única forma atual de exportar DXF de um esboço
  via API, já que `Sketch.saveAsDXF` foi retirado. Se a Autodesk mudar a
  assinatura, o único lugar a ajustar é `fusion_adapter/exporter.py::export_dxf`.
- O quadro "Quantidade por peça" é global (ver Decisões acima).
- Peças cujo maior contorno tenha furos/dentes muito próximos da borda podem,
  em teoria, ter o casco convexo do contorno aproximado (usado só para
  nesting) ligeiramente maior que o contorno exato; isso é inerente a usar o
  retângulo envolvente do casco convexo para o nesting (não afeta a geometria
  exportada, só a decisão de encaixe).

## Checklist de aceitação (teste manual dentro do Fusion)

Rode o comando **Criar peças de teste** primeiro; ele cria um documento novo
com 4 corpos. Depois use **Nest Faces (Laser)** selecionando a face de maior
área de cada um.

| # | Passo | Resultado esperado |
|---|-------|---------------------|
| 1 | Rodar "Criar peças de teste" | Documento novo com 4 corpos: retângulo c/ furo, peça com dentes de encaixe, círculo, peça extrudada no plano YZ. |
| 2 | Rodar "Nest Faces (Laser)", selecionar as 4 faces de maior área (uma por corpo) | Filtro de seleção só aceita faces planas; diálogo abre normalmente. |
| 3 | Selecionar sem querer as duas faces (topo e fundo) do mesmo corpo | Mensagem de **aviso** aparece, mas o comando **continua** (não trava). |
| 4 | Rodar com Rotação = "Automática", chapa 600×400, espaçamento 3, margem 5 | Relatório mostra todas as 4 peças alocadas em 1 chapa, sem sobreposição visível no esboço. |
| 5 | Peça extrudada no plano YZ | Aparece corretamente **nivelada** (plana, no XY do novo componente), não distorcida nem espelhada. |
| 6 | Peça com furo | O esboço mostra o contorno externo e o furo como um loop interno separado, na posição correta dentro do contorno. |
| 6b | **Cantos arredondados da peça 1 (fillet, raio 8 mm)** | O contorno fecha **sem nenhum buraco/gap** nos 4 cantos arredondados — nem no esboço do Fusion, nem no SVG/DXF exportado. Esse é o caso que expôs o bug de `Arc3D.getData()` usar o `referenceVector` da curva em vez do eixo +X global; confira principalmente aqui. |
| 7 | Peça com dentes de encaixe | Todos os cantos retos preservados exatamente (sem arredondar/aproximar). |
| 8 | Reduzir a chapa para 50×50 mm e rodar de novo | Relatório lista peças "não alocadas" em vez de travar ou lançar erro. |
| 9 | Conferir o componente `NEST_<data-hora>` | O design original não foi alterado; `Ctrl+Z` desfaz a operação inteira num passo só. |
| 10 | Marcar "Exportar DXF/SVG" com uma pasta válida | Um `.dxf` e um `.svg` por chapa aparecem na pasta escolhida. |
| 11 | Abrir o `.svg` gerado num navegador | Contorno externo azul, furo vermelho, contorno da chapa cinza tracejado; nada preenchido. |
| 12 | Abrir o `.dxf` no LightBurn/RDWorks (ou AutoCAD) | Geometria em mm, sem o retângulo da chapa (é construção, não exportada) e sem pontos soltos. |
| 13 | Forçar um erro (ex.: apagar a pasta de saída entre escolher e clicar OK) | Mensagem curta em pt-BR aparece; `log.txt` na pasta do add-in recebe o traceback completo; nenhum esboço "pela metade" fica no design. |

## Comandos úteis

```powershell
# Instalar/atualizar o add-in no Fusion
.\install.ps1
```

```bash
# Rodar os testes automatizados
pip install -r requirements-dev.txt
pytest FusionLaserNest/tests -q
```
