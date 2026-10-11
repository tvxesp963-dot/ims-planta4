/* uso-lecturas.js — cuenta las lecturas de Firestore que hace esta app y las suma por día.
 *
 * Uso: cargarlo DESPUÉS de firebase-firestore-compat y ANTES de que la app lea datos:
 *   <script src="uso-lecturas.js" data-app="BOM Simulator"></script>
 *
 * Qué cuenta (igual que la factura de Firestore):
 *   - get() de una colección o consulta: 1 lectura por documento (mínimo 1 si viene vacía).
 *   - get() de un documento: 1 lectura.
 *   - onSnapshot: la primera carga cuenta todos los documentos; después solo los que cambian.
 *   - Lo que sale de la caché del navegador no se cobra y no se cuenta.
 * Guarda en  uso_lecturas/<día>  (día = hora del Pacífico, que es cuando Firebase reinicia la cuota gratis):
 *   { total, apps: {app: n}, colls: {colección: n}, ac: {"app › colección": n} }
 * Escribe como máximo una vez cada 5 minutos por pestaña, y solo si hubo lecturas nuevas.
 * No cuenta las lecturas de la propia colección uso_lecturas.
 */
(function () {
  if (window.__usoLecturasOn) return;
  if (typeof firebase === 'undefined' || !firebase.firestore || !firebase.firestore.Query || !firebase.firestore.DocumentReference) return;
  window.__usoLecturasOn = true;

  var tag = document.currentScript;
  var APP = (tag && tag.getAttribute('data-app')) || (location.pathname.split('/').pop() || 'app').replace(/\.html$/, '') || 'app';
  var COLECCION = 'uso_lecturas';
  var CADA_MS = 5 * 60 * 1000;
  var buf = { total: 0, colls: {} };
  var fsRef = null;

  function limpia(s) { return String(s).replace(/[.\/\[\]*`~]/g, '_').slice(0, 80) || '_'; }
  function dia() {
    try { return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' }); }
    catch (e) { return new Date().toISOString().slice(0, 10); }
  }
  function suma(coll, n) {
    if (!(n > 0)) return;
    coll = limpia(coll || '_');
    if (coll === COLECCION) return;
    buf.total += n;
    buf.colls[coll] = (buf.colls[coll] || 0) + n;
  }
  function cuentaDocs(snap) {
    var docs = snap && snap.docs;
    if (!docs) return;
    if (!docs.length) { suma('(vacía)', 1); return; }
    var por = {};
    for (var i = 0; i < docs.length; i++) {
      var id = docs[i].ref && docs[i].ref.parent ? docs[i].ref.parent.id : '_';
      por[id] = (por[id] || 0) + 1;
    }
    for (var k in por) suma(k, por[k]);
  }
  function cuentaCambios(snap) {
    var ch = snap.docChanges ? snap.docChanges() : [];
    for (var i = 0; i < ch.length; i++) {
      var id = ch[i].doc && ch[i].doc.ref && ch[i].doc.ref.parent ? ch[i].doc.ref.parent.id : '_';
      suma(id, 1);
    }
  }
  function desdeCache(snap) { return !!(snap && snap.metadata && snap.metadata.fromCache); }

  var Q = firebase.firestore.Query.prototype;
  var D = firebase.firestore.DocumentReference.prototype;

  var qGet = Q.get;
  Q.get = function () {
    var self = this; fsRef = fsRef || self.firestore;
    return qGet.apply(this, arguments).then(function (snap) {
      try { if (!desdeCache(snap)) cuentaDocs(snap); } catch (e) {}
      return snap;
    });
  };
  var dGet = D.get;
  D.get = function () {
    var self = this; fsRef = fsRef || self.firestore;
    return dGet.apply(this, arguments).then(function (snap) {
      try { if (!desdeCache(snap)) suma(self.parent && self.parent.id, 1); } catch (e) {}
      return snap;
    });
  };

  // onSnapshot acepta (next, error), (opciones, next, error) u (observador). Se envuelve la función "next".
  function envuelve(esDoc, ref) {
    var primera = true;
    return function (fn) {
      return function (snap) {
        try {
          if (!desdeCache(snap)) {
            if (esDoc) suma(ref.parent && ref.parent.id, 1);
            else if (primera) cuentaDocs(snap);
            else cuentaCambios(snap);
          }
          primera = false;
        } catch (e) {}
        return fn.apply(this, arguments);
      };
    };
  }
  function parcheaSnapshot(proto, esDoc) {
    var orig = proto.onSnapshot;
    proto.onSnapshot = function () {
      fsRef = fsRef || this.firestore;
      var args = Array.prototype.slice.call(arguments);
      var wrap = envuelve(esDoc, this);
      var i = 0;
      if (args[0] && typeof args[0] === 'object' && typeof args[0].next !== 'function') i = 1; // opciones
      if (typeof args[i] === 'function') args[i] = wrap(args[i]);
      else if (args[i] && typeof args[i].next === 'function') {
        var o = args[i], nextOrig = o.next;
        args[i] = { next: wrap(nextOrig), error: o.error, complete: o.complete };
      }
      return orig.apply(this, args);
    };
  }
  parcheaSnapshot(Q, false);
  parcheaSnapshot(D, true);

  function vuelca() {
    if (!buf.total || !fsRef) return;
    var total = buf.total, colls = buf.colls;
    buf = { total: 0, colls: {} };
    try {
      var inc = firebase.firestore.FieldValue.increment;
      var data = { total: inc(total), apps: {}, colls: {}, ac: {}, actualizado: Date.now() };
      var app = limpia(APP);
      data.apps[app] = inc(total);
      for (var c in colls) { data.colls[c] = inc(colls[c]); data.ac[app + ' › ' + c] = inc(colls[c]); }
      fsRef.collection(COLECCION).doc(dia()).set(data, { merge: true }).catch(function () {
        // Si no se pudo guardar (sin red o sin permiso), se devuelve al contador para el siguiente intento.
        buf.total += total; for (var k in colls) buf.colls[k] = (buf.colls[k] || 0) + colls[k];
      });
    } catch (e) {}
  }
  setInterval(vuelca, CADA_MS);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') vuelca(); });
  window.addEventListener('pagehide', vuelca);
  window.__usoLecturas = { vuelca: vuelca, pendiente: function () { return buf.total; }, app: APP };
})();
