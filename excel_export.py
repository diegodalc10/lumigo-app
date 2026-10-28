"""Portable XLSX response writer for the Python application (standard OOXML).

No external service, macros, external links or executable spreadsheet formulas.
All user-provided fields are emitted as literal text, never as Excel formulas.
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape
from datetime import datetime, timezone, timedelta

SS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'

def txt(value):
    return escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value)))

def col(index):
    out=''
    while index:
        index,rem=divmod(index-1,26);out=chr(65+rem)+out
    return out

def sheet_xml(rows,drawing=False):
    data=[]
    for ri,row in enumerate(rows,1):
        cells=[]
        for ci,value in enumerate(row,1):
            if value is None: continue
            style=1 if ri==1 else 2 if isinstance(value,(int,float)) and not isinstance(value,bool) else 0
            ref=col(ci)+str(ri)
            if isinstance(value,(int,float)) and not isinstance(value,bool): cell=f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
            else: cell=f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{txt(value)}</t></is></c>'
            cells.append(cell)
        data.append(f'<row r="{ri}" ht="22" customHeight="1">'+''.join(cells)+'</row>')
    cols='<cols><col min="1" max="1" width="32" customWidth="1"/><col min="2" max="3" width="28" customWidth="1"/><col min="4" max="10" width="24" customWidth="1"/></cols>'
    return f'<worksheet xmlns="{SS}" xmlns:r="{REL}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>{cols}<sheetData>'+''.join(data)+'</sheetData>'+ (f'<drawing r:id="rId1"/>' if drawing else '')+'</worksheet>'

def chart_xml(series,categories,sheet,donut=False):
    ns='http://schemas.openxmlformats.org/drawingml/2006/chart'
    cats=''.join(f'<c:pt idx="{i}"><c:v>{txt(v)}</c:v></c:pt>' for i,v in enumerate(categories))
    rows=len(categories)
    parts=[]
    for j,(label,values) in enumerate(series):
        nums=''.join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i,v in enumerate(values))
        parts.append(f'<c:ser><c:idx val="{j}"/><c:order val="{j}"/><c:tx><c:v>{txt(label)}</c:v></c:tx><c:cat><c:strRef><c:f>\'{sheet}\'!$A$2:$A${rows+1}</c:f><c:strCache><c:ptCount val="{rows}"/>{cats}</c:strCache></c:strRef></c:cat><c:val><c:numRef><c:f>\'{sheet}\'!${col(j+2)}$2:${col(j+2)}${rows+1}</c:f><c:numCache><c:formatCode>#,##0</c:formatCode><c:ptCount val="{rows}"/>{nums}</c:numCache></c:numRef></c:val></c:ser>')
    if donut: plot='<c:doughnutChart><c:varyColors val="1"/>'+''.join(parts)+'<c:holeSize val="65"/></c:doughnutChart>'
    else:
        plot='<c:lineChart><c:grouping val="standard"/>'+''.join(parts)+'<c:axId val="10"/><c:axId val="20"/></c:lineChart>'
        plot+='<c:catAx><c:axId val="10"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/><c:crossAx val="20"/><c:crosses val="autoZero"/></c:catAx><c:valAx><c:axId val="20"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="l"/><c:numFmt formatCode="#,##0" sourceLinked="0"/><c:crossAx val="10"/><c:crosses val="autoZero"/></c:valAx>'
    return f'<c:chartSpace xmlns:c="{ns}"><c:style val="10"/><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/>{plot}</c:plotArea><c:legend><c:legendPos val="b"/></c:legend><c:plotVisOnly val="1"/></c:chart></c:chartSpace>'

def report_workbook(d,records,products):
    date=lambda t:datetime.fromtimestamp(t,timezone(timedelta(hours=-5))).strftime('%Y-%m-%d %H:%M:%S')
    summary=[['LumiGo · Dashboard','DEMO · Sin dinero real'],['Perfil',d['role']],['Generado en Bogotá',date(d['generated_at'])],['Período dashboard',str(d['days'])+' días, sujeto al reinicio de vista'],['Detalle histórico','Las hojas Registros y Productos incluyen todo el historial autorizado y catálogo actual'],['Indicador','Valor','Alcance']]+[[m['label'],m['value'],m['hint']] for m in d['metrics']]
    sheets=[('Dashboard',summary),('Registros',[['Referencia','Fecha Bogotá','Tipo','Comercio','Producto al comprar','Usuario','Puntos']]+[[r['reference'],date(r['timestamp']),r['type'],r['store'],r['product'],r['customer'],r['amount']] for r in records]),('Productos',[['ID','Producto actual','Comercio','Precio actual en puntos','Stock actual']]+[[p['id'],p['name'],p['store'],p['price'],p['stock']] for p in products]),('Actividad',[['Fecha',*d['series_labels']]]+[[p['date'],p['first'],p['second']] for p in d['series']]),('Distribucion',[['Categoría','Valor']]+[[p['label'],p['value']] for p in d['composition']])]
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        defaults='<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        overrides='<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        overrides+=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,6))
        overrides+='<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'+''.join(f'<Override PartName="/xl/charts/chart{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>' for i in (1,2))
        z.writestr('[Content_Types].xml',f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{defaults}{overrides}</Types>')
        z.writestr('_rels/.rels',f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{SS}" xmlns:r="{REL}"><sheets>'+''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',f'<Relationships xmlns="{PKG}">'+''.join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,6))+f'<Relationship Id="rId6" Type="{REL}/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{SS}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="12"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF12334B"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"/><xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i,(_,rows) in enumerate(sheets,1): z.writestr(f'xl/worksheets/sheet{i}.xml',sheet_xml(rows,i==1))
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels',f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
        anchors=''
        for i,row in [(1,1),(2,20)]:
            anchors+=f'<xdr:twoCellAnchor><xdr:from><xdr:col>4</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>13</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{row+17}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{i}" name="Gráfica {i}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="rId{i}"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>'
        z.writestr('xl/drawings/drawing1.xml',f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{REL}">{anchors}</xdr:wsDr>')
        z.writestr('xl/drawings/_rels/drawing1.xml.rels',f'<Relationships xmlns="{PKG}">'+''.join(f'<Relationship Id="rId{i}" Type="{REL}/chart" Target="../charts/chart{i}.xml"/>' for i in (1,2))+'</Relationships>')
        z.writestr('xl/charts/chart1.xml',chart_xml([(label,[p[key] for p in d['series']]) for label,key in zip(d['series_labels'],('first','second'))],[p['date'] for p in d['series']],'Actividad'))
        z.writestr('xl/charts/chart2.xml',chart_xml([('Distribución',[p['value'] for p in d['composition']])],[p['label'] for p in d['composition']],'Distribucion',True))
    return out.getvalue()
