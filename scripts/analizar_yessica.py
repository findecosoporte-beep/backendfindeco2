"""Análisis puntual del préstamo 260621 (YESSICA)."""
from datetime import date
from decimal import Decimal

from api.core.cuotas import extract_cuota_numero_from_documento
from api.models import Pago, Prestamo, PrestamoCuota

p = Prestamo.objects.select_related('id_cliente', 'id_cartera', 'id_zona', 'id_usuario').get(
    numero_prestamo='260621'
)
c = p.id_cliente
print('=== CLIENTE ===')
print(f'  id={c.id_cliente} nombre={c.nombre!r} dni={c.dni} telefono={c.telefono}')
print(f'  dia_cobro_semanal={getattr(c, "dia_cobro_semanal", None)}')
print()
print('=== PRESTAMO #10 | 260621 ===')
print(f'  estado={p.estado} | monto={p.monto} | plazo={p.plazo} meses')
print(f'  forma_pago={p.forma_pago} | tasa={p.tasa_interes}% | comision={p.comision}')
print(f'  fecha_entrega={p.fecha_entrega} ({p.fecha_entrega.strftime("%A")})')
print(f'  fecha_vencimiento={p.fecha_vencimiento} ({p.fecha_vencimiento.strftime("%A")})')
print(f'  dias_mora={p.dias_mora} | producto={p.producto!r}')
print(f'  asesor={p.asesor!r} | sucursal={p.sucursal!r}')
if p.id_cartera_id:
    print(f'  cartera={p.id_cartera.nombre} dia_cobro={p.id_cartera.dia_cobro}')
if p.id_zona_id:
    print(f'  zona={p.id_zona.nombre}')
print()
cuotas = list(PrestamoCuota.objects.filter(id_prestamo=p).order_by('numero_cuota'))
print(f'=== PLAN DE CUOTAS ({len(cuotas)} cuotas) ===')
total_prog = Decimal('0')
total_cap = Decimal('0')
total_int = Decimal('0')
for cu in cuotas:
    wd = cu.fecha_programada.strftime('%a')
    print(
        f'  #{cu.numero_cuota:2d} | {cu.fecha_programada} ({wd}) | '
        f'total={cu.total_programado} cap={cu.capital_programado} int={cu.interes_programado} '
        f'saldo_cap={cu.saldo_capital_programado}'
    )
    total_prog += cu.total_programado
    total_cap += cu.capital_programado
    total_int += cu.interes_programado
print(f'  SUMA capital_programado: {total_cap}')
print(f'  SUMA interes_programado: {total_int}')
print(f'  SUMA total_programado: {total_prog}')
print()
pagos = list(Pago.objects.filter(id_prestamo=p).order_by('fecha_pago', 'id_pago'))
print(f'=== PAGOS ({len(pagos)}) ===')
if not pagos:
    print('  (ninguno)')
for pg in pagos:
    print(
        f'  #{pg.id_pago} | {pg.fecha_pago} | doc={pg.documento!r} '
        f'cap={pg.capital} int={pg.interes} mora={pg.mora} saldo={pg.saldo}'
    )
print()
hoy = date.today()
paid = set()
for pg in pagos:
    n = extract_cuota_numero_from_documento(pg.documento)
    if n:
        paid.add(n)
atrasadas = [cu for cu in cuotas if cu.numero_cuota not in paid and cu.fecha_programada < hoy]
sig = next((cu for cu in cuotas if cu.numero_cuota not in paid), None)
print(f'=== ESTADO AL {hoy} ===')
print(f'  SALDO INICIAL: {p.monto}')
print(f'  SALDO ACTUAL: {pagos[-1].saldo if pagos else p.monto}')
print(f'  CUOTA (hoja cobros): {cuotas[0].total_programado if cuotas else p.monto}')
print(f'  Cuotas pagadas: {sorted(paid) if paid else "ninguna"}')
print(f'  Cuotas atrasadas: {len(atrasadas)} {[x.numero_cuota for x in atrasadas]}')
if sig:
    dias_faltan = (sig.fecha_programada - hoy).days
    print(
        f'  Proxima cuota: #{sig.numero_cuota} vence {sig.fecha_programada} '
        f'(en {dias_faltan} dias) monto {sig.total_programado}'
    )
print()
otros = Prestamo.objects.filter(id_cliente=c).exclude(pk=p.pk)
print('=== OTROS PRESTAMOS MISMO CLIENTE ===')
for op in otros:
    ncu = PrestamoCuota.objects.filter(id_prestamo=op).count()
    np = Pago.objects.filter(id_prestamo=op).count()
    print(f'  #{op.id_prestamo} {op.numero_prestamo} estado={op.estado} monto={op.monto} cuotas={ncu} pagos={np}')
