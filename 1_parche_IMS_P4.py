# -*- coding: utf-8 -*-
# PARCHE IMS P4 v2: al RECIBIR el pallet de Gift Box (Top) / Lower Box (Bottom):
#  1) MUESTRA una vista previa (qué entra, qué se descuenta, qué no se toca, qué problemas hay) y pide confirmar.
#  2) Si confirmas, registra la entrada y descuenta Sheet y Chip Board. Si cancelas, no pasa nada (el pallet queda PENDIENTE).
# Correr desde la raiz de IMS-Deploy (donde existe public\index.html):  python parche_IMS_P4_medio_proceso.py
import sys

RUTA = 'public/index.html'

NUEVO_JS = r"""/* ── MEDIO PROCESO: vista previa + descuento de Sheet y Chip Board al RECIBIR el pallet ── */
const COMP_MEDIO = {
  'GIFT BOX (TOP)': ['SHEET TOP BOX','CHIP BOARD TOP (RANURADO)'],
  'LOWER BOX (BOTTOM)': ['SHEET LOWER BOX (BOTTOM)','CHIP BOARD BOTTOM (RANURADO)']
};
var _bomMedioCache = null;
async function bomActivoMedio(){
  if (_bomMedioCache && (Date.now() - _bomMedioCache.t) < 600000) return _bomMedioCache.bom;
  const d = await db.collection('bom_simulator_p4').doc('bom_activo').get();
  const bom = d.exists ? JSON.parse(d.data().bom || '[]') : [];
  _bomMedioCache = {t: Date.now(), bom: bom};
  return bom;
}
/* Calcula el plan SIN tocar nada. */
async function planComponentesMedio(item, qty, modelo){
  const nU = x => String(x || '').trim().toUpperCase();
  const dsc0 = nU(item.desc);
  const plan = {aplica: false, comps: [], problemas: [], modelo: modelo || ''};
  const todos = [].concat(COMP_MEDIO['GIFT BOX (TOP)'], COMP_MEDIO['LOWER BOX (BOTTOM)']);
  if (todos.indexOf(dsc0) >= 0) {
    plan.aplica = true;
    plan.problemas.push('Estás recibiendo un pallet de medio proceso sobre "' + item.desc + '" (es un componente). Cancela y selecciona Gift Box (Top) o Lower Box (Bottom).');
    return plan;
  }
  const lista = COMP_MEDIO[dsc0];
  if (!lista) return plan;
  plan.aplica = true;
  if (!nU(modelo)) { plan.problemas.push('El pallet no trae modelo: NO se puede saber qué Sheet/Chip Board descontar.'); return plan; }
  let bom;
  try { bom = await bomActivoMedio(); }
  catch(e) { plan.problemas.push('No se pudo leer el BOM (' + e.message + '): NO se descontarán Sheet ni Chip Board.'); return plan; }
  for (const dsc of lista) {
    const fila = bom.find(b => b.pn && b.sm && nU(b.sm) === nU(modelo) && nU(b.desc) === dsc);
    if (!fila) { plan.problemas.push(dsc + ': no está en el BOM del modelo ' + modelo + ' (NO se descontará).'); continue; }
    const it = items.find(i => nU(i.pn) === nU(fila.pn) && nU(i.desc) === dsc);
    if (!it) { plan.problemas.push(fila.pn + ' ' + dsc + ': no existe en el IMS (NO se descontará).'); continue; }
    const a0 = parseFloat(it.actual) || 0;
    const aplicado = Math.min(qty, Math.max(0, a0));
    plan.comps.push({it: it, fila: fila, dsc: dsc, antes: a0, aplicado: aplicado, faltante: qty - aplicado});
    if (qty - aplicado > 0) plan.problemas.push(fila.pn + ' ' + dsc + ': solo hay ' + a0.toLocaleString() + ' y se necesitan ' + qty.toLocaleString() + ' (quedará en 0, faltan ' + (qty - aplicado).toLocaleString() + ').');
  }
  return plan;
}
function textoPlanMedio(item, qty, palletId, plan){
  const a = parseFloat(item.actual) || 0;
  let t = '📦 RECEPCIÓN DE MEDIO PROCESO\nPallet: ' + palletId + (plan.modelo ? '  ·  Modelo: ' + plan.modelo : '') + '\n\n';
  t += '➕ ENTRA:\n   ' + item.pn + ' · ' + item.desc + '   +' + qty.toLocaleString() + '   (' + a.toLocaleString() + ' → ' + (a + qty).toLocaleString() + ')\n\n';
  t += '➖ SE DESCUENTA (componentes ya consumidos al fabricar este medio proceso):\n';
  if (!plan.comps.length) t += '   (nada)\n';
  plan.comps.forEach(c => { t += '   ' + c.fila.pn + ' · ' + c.dsc + '   -' + c.aplicado.toLocaleString() + '   (' + c.antes.toLocaleString() + ' → ' + (c.antes - c.aplicado).toLocaleString() + ')\n'; });
  t += '\n✋ NO se toca ningún otro material.\n';
  if (plan.problemas.length) t += '\n⚠️ AVISOS:\n - ' + plan.problemas.join('\n - ') + '\n';
  t += '\n¿Confirmar? (Cancelar = no se registra nada y el pallet sigue PENDIENTE)';
  return t;
}
/* Ejecuta el plan ya confirmado. Devuelve '' si todo bien o un mensaje de aviso. */
async function ejecutarComponentesMedio(plan, qty, palletId){
  const fallos = [];
  const iso = new Date().toISOString();
  for (const c of plan.comps) {
    const it = c.it;
    const a0 = parseFloat(it.actual) || 0;
    const aplicado = Math.min(qty, Math.max(0, a0));
    const faltante = qty - aplicado;
    const antes = {salidas: it.salidas, actual: it.actual};
    it.salidas = (parseFloat(it.salidas) || 0) + qty;
    it.actual = a0 - aplicado;
    const refTxt = 'MEDIO PROCESO · ' + palletId;
    const hItem = {tipo: 'S', fecha: iso, qty: qty, loc: it.ubicacion || 'Almacén', user: user.name, ref: refTxt};
    if (!it.historial) it.historial = [];
    it.historial.push(hItem);
    const mov = {tipo: 'S', pn: it.pn, desc: it.desc, familia: it.familia, qty: qty, fecha: iso, user: user.name, ref: refTxt, stock: it.actual, loc: it.ubicacion || 'Almacén', origen: 'MEDIO_PROCESO', pallet: palletId, faltante: faltante};
    movs.unshift(mov);
    saveLocal();
    const res = await pushMov(mov, {entradas: 0, salidas: qty, actual: -aplicado}, hItem);
    if (!res.ok) {
      it.salidas = antes.salidas; it.actual = antes.actual; it.historial.pop(); movs.shift(); saveLocal();
      fallos.push(c.fila.pn + ' (' + c.dsc + '): ' + res.err);
    }
  }
  if (fallos.length) return '⚠️ La entrada SÍ se registró, pero NO se pudo descontar:\n- ' + fallos.join('\n- ') + '\n\nCorrígelo con un AJUSTE en Movimientos.';
  return '';
}
"""

CAMBIOS = [
    ("version (fuerza recarga en celulares)",
     'var APP_VERSION = "20261014a";',
     'var APP_VERSION = "20261016b";'),
    ("funciones de vista previa y descuento",
     'function checkViewerPass() {',
     NUEVO_JS + '\nfunction checkViewerPass() {'),
    ("reclamarPallet devuelve el modelo",
     "return {ok:true,maq:d.data().maquina||''};",
     "return {ok:true,maq:d.data().maquina||'',modelo:d.data().modelo||''};"),
    ("variable del plan",
     "let palletInfo = null, claveManualOk = false;",
     "let palletInfo = null, claveManualOk = false, planMedio = null;"),
    ("vista previa y confirmacion",
     "palletInfo = {id:scanPallet.id, maq:rc.maq||''};",
     """palletInfo = {id:scanPallet.id, maq:rc.maq||'', modelo:rc.modelo||''};
    planMedio = await planComponentesMedio(item, qty, palletInfo.modelo);
    if (planMedio.aplica && !confirm(textoPlanMedio(item, qty, palletInfo.id, planMedio))) {
      await liberarPallet(palletInfo.id); scanPallet=null; limpiarFormMov();
      toast('Recepción cancelada: el pallet sigue PENDIENTE','err'); return;
    }"""),
    ("descuento de componentes tras la entrada",
     "if (movTipo==='E') await marcarPalletRecibido(ref);",
     """let avisoComp = '';
  if (planMedio && planMedio.aplica && planMedio.comps.length) avisoComp = await ejecutarComponentesMedio(planMedio, qty, palletInfo.id);
  if (movTipo==='E') await marcarPalletRecibido(ref);"""),
    ("aviso final si algo fallo",
     "toast(lbl[movTipo]+': '+qty.toLocaleString()+' pzas · '+item.pn,'ok');",
     "toast(lbl[movTipo]+': '+qty.toLocaleString()+' pzas · '+item.pn,'ok');\n  if (avisoComp) alert(avisoComp);"),
]

with open(RUTA, encoding='utf-8', newline='') as f:
    txt = f.read()
for nombre, viejo, nuevo in CAMBIOS:
    n = txt.count(viejo)
    if n != 1:
        print('NO ENCONTRADO (%d veces): %s  -> no se modifico nada' % (n, nombre))
        sys.exit(1)
    txt = txt.replace(viejo, nuevo)
    print('OK: ' + nombre)
with open(RUTA, 'w', encoding='utf-8', newline='') as f:
    f.write(txt)
print('Listo. public/index.html del IMS P4 actualizado.')
