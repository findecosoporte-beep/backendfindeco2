"""Pruebas unitarias de utilidades compartidas en api.core."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from api.core.cuotas import extract_cuota_numero_from_documento
from api.core.fechas import (
    add_months,
    align_weekday_on_or_after,
    calculate_fecha_cuota,
    calculate_fecha_vencimiento,
    weekday_from_dia_cobro,
)
from api.core.money import round_money
from api.core.prestamo_calc import (
    annual_rate_from_nominal,
    frecuencia_anual,
    interes_total_pct_semanal,
    periodic_rate_from_nominal,
    periodos_desde_plazo,
    periods_from_months,
    plan_totales_desde_condiciones,
    tasa_periodica_para_calculo,
    tasa_semanal_negocio,
    tasa_mensual_negocio,
    interes_total_pct_mensual,
)
from api.core.reporte_saldos import saldo_pendiente_desde_plan, total_compromiso_desde_plan
from api.core.distribucion_pago import (
    abonado_por_cuota_desde_pagos,
    distribuir_cobro_con_excedente_a_capital,
    distribuir_monto_en_cuotas,
    pendiente_cuota,
    saldo_pendiente_con_abonos,
)


class CoreCuotasTestCase(SimpleTestCase):
    """Extracción de número de cuota desde documento."""

    def test_extract_cuota_con_texto_estandar(self):
        self.assertEqual(extract_cuota_numero_from_documento('Cuota 3'), 3)

    def test_extract_cuota_case_insensitive(self):
        self.assertEqual(extract_cuota_numero_from_documento('cuota 12'), 12)

    def test_extract_cuota_vacio_retorna_none(self):
        self.assertIsNone(extract_cuota_numero_from_documento(''))
        self.assertIsNone(extract_cuota_numero_from_documento(None))

    def test_extract_cuota_sin_numero_retorna_none(self):
        self.assertIsNone(extract_cuota_numero_from_documento('Pago parcial'))


class CoreMoneyTestCase(SimpleTestCase):
    """Redondeo monetario HALF_UP."""

    def test_round_money_half_up(self):
        self.assertEqual(round_money(Decimal('1.005')), Decimal('1.01'))

    def test_round_money_dos_decimales(self):
        self.assertEqual(round_money(Decimal('10.1')), Decimal('10.10'))


class CorePrestamoCalcTestCase(SimpleTestCase):
    """Tasas y periodos de préstamo."""

    def test_periods_semanal_12_semanas(self):
        self.assertEqual(periodos_desde_plazo(12, 'semanal'), 12)
        self.assertEqual(periods_from_months(12, 'semanal'), 12)

    def test_periods_quincenal_12_meses(self):
        self.assertEqual(periods_from_months(12, 'quincenal'), 24)

    def test_periods_mensual_12_meses(self):
        self.assertEqual(periods_from_months(12, 'mensual'), 12)

    def test_tasa_semanal_negocio(self):
        for semanas in (2, 4, 6, 8, 10, 12, 16):
            self.assertEqual(tasa_semanal_negocio(semanas), Decimal('2.5'))

    def test_tasa_mensual_negocio(self):
        for meses in (1, 3, 6, 12, 24):
            self.assertEqual(tasa_mensual_negocio(meses), Decimal('10'))

    def test_interes_total_pct_semanal_12_semanas_es_30_por_ciento(self):
        self.assertEqual(interes_total_pct_semanal(12), Decimal('30.0'))
        self.assertEqual(interes_total_pct_semanal(6), Decimal('15'))
        self.assertEqual(interes_total_pct_semanal(8), Decimal('20'))
        self.assertEqual(interes_total_pct_semanal(10), Decimal('25'))
        self.assertEqual(interes_total_pct_semanal(16), Decimal('40'))
        self.assertEqual(interes_total_pct_semanal(4), Decimal('10'))
        self.assertEqual(interes_total_pct_semanal(2), Decimal('5'))

    def test_interes_total_pct_mensual(self):
        self.assertEqual(interes_total_pct_mensual(6), Decimal('60'))
        self.assertEqual(interes_total_pct_mensual(12), Decimal('120'))
        self.assertEqual(interes_total_pct_mensual(3), Decimal('30'))

    def test_tasa_periodica_mensual(self):
        self.assertEqual(
            tasa_periodica_para_calculo(Decimal('99.00'), 'mensual', 12),
            Decimal('10'),
        )

    def test_tasa_periodica_semanal_6_semanas(self):
        self.assertEqual(
            tasa_periodica_para_calculo(Decimal('99.00'), 'semanal', 6),
            Decimal('2.5'),
        )

    def test_periodic_rate_quincenal(self):
        self.assertEqual(
            periodic_rate_from_nominal(Decimal('12.00'), 'quincenal'),
            Decimal('6.00'),
        )

    def test_frecuencia_anual(self):
        self.assertEqual(frecuencia_anual('mensual'), 12)
        self.assertEqual(frecuencia_anual('semanal'), 52)

    def test_annual_rate_from_nominal_positiva(self):
        tasa = annual_rate_from_nominal(Decimal('1.00'))
        self.assertGreater(tasa, Decimal('0'))


class CoreFechasTestCase(SimpleTestCase):
    """Fechas de vencimiento y cuotas."""

    def test_add_months_preserva_dia_valido(self):
        base = date(2025, 1, 31)
        self.assertEqual(add_months(base, 1), date(2025, 2, 28))

    def test_calculate_fecha_vencimiento_mensual(self):
        entrega = date(2025, 1, 15)
        self.assertEqual(
            calculate_fecha_vencimiento(entrega, 3, 'mensual'),
            date(2025, 4, 15),
        )

    def test_calculate_fecha_cuota_semanal(self):
        entrega = date(2025, 1, 1)
        self.assertEqual(
            calculate_fecha_cuota(entrega, 2, 'semanal'),
            date(2025, 1, 15),
        )

    def test_calculate_fecha_cuota_mensual_alinea_dia_cartera(self):
        entrega = date(2026, 6, 25)  # jueves
        self.assertEqual(
            calculate_fecha_cuota(entrega, 1, 'mensual', 'lunes'),
            date(2026, 7, 27),
        )
        self.assertEqual(
            calculate_fecha_cuota(entrega, 2, 'mensual', 'lunes'),
            date(2026, 8, 31),
        )

    def test_calculate_fecha_cuota_semanal_alinea_dia_cartera(self):
        entrega = date(2026, 6, 25)  # jueves
        cuota1 = calculate_fecha_cuota(entrega, 1, 'semanal', 'martes')
        self.assertEqual(cuota1.weekday(), weekday_from_dia_cobro('martes'))
        self.assertEqual(cuota1, date(2026, 6, 30))
        cuota2 = calculate_fecha_cuota(entrega, 2, 'semanal', 'martes')
        self.assertEqual(cuota2, date(2026, 7, 7))

    def test_calculate_fecha_cuota_semanal_lunes_desde_domingo_entrega(self):
        """Desembolso domingo: primera cuota cae el lunes siguiente."""
        entrega = date(2026, 6, 21)  # domingo
        cuota1 = calculate_fecha_cuota(entrega, 1, 'semanal', 'lunes')
        self.assertEqual(cuota1, date(2026, 6, 22))
        self.assertEqual(cuota1.weekday(), 0)

    def test_calculate_fecha_cuota_semanal_lunes_desde_lunes_entrega(self):
        """Desembolso lunes: primera cuota cae el lunes de la semana siguiente."""
        entrega = date(2026, 6, 22)  # lunes
        cuota1 = calculate_fecha_cuota(entrega, 1, 'semanal', 'lunes')
        self.assertEqual(cuota1, date(2026, 6, 29))
        self.assertEqual(cuota1.weekday(), 0)

    def test_calculate_fecha_vencimiento_usa_ultima_cuota_alineada(self):
        entrega = date(2026, 6, 25)
        vencimiento = calculate_fecha_vencimiento(entrega, 3, 'mensual', 'lunes')
        self.assertEqual(vencimiento, calculate_fecha_cuota(entrega, 3, 'mensual', 'lunes'))
        self.assertEqual(vencimiento.weekday(), 0)

    def test_align_weekday_on_or_after_mismo_dia(self):
        lunes = date(2026, 6, 22)
        self.assertEqual(align_weekday_on_or_after(lunes, 0), lunes)


class CoreReporteSaldosTestCase(SimpleTestCase):
    """Saldos capital+interés para hoja de cobros."""

    def test_plan_totales_yessica(self):
        total, primera = plan_totales_desde_condiciones(
            Decimal('10000.00'),
            3,
            'semanal',
            Decimal('10.00'),
        )
        self.assertEqual(primera, Decimal('4333.33'))
        self.assertEqual(total, Decimal('13000.00'))

    def test_saldo_pendiente_resta_cuotas_pagadas(self):
        class Cuota:
            def __init__(self, n, total):
                self.numero_cuota = n
                self.total_programado = Decimal(total)
                self.servicios_programado = Decimal('0')
                self.otros_programado = Decimal('0')

        plan = [Cuota(1, '1050.00'), Cuota(2, '1050.00'), Cuota(3, '1050.00')]
        self.assertEqual(total_compromiso_desde_plan(plan), Decimal('3150.00'))
        self.assertEqual(saldo_pendiente_desde_plan(plan, paid_nums={1}), Decimal('2100.00'))


class CoreDistribucionPagoTestCase(SimpleTestCase):
    """Reparto de cobros con excedente entre cuotas."""

    class Cuota:
        def __init__(
            self,
            n,
            capital,
            interes,
            total=None,
            saldo_capital=None,
        ):
            self.numero_cuota = n
            self.capital_programado = Decimal(capital)
            self.interes_programado = Decimal(interes)
            self.total_programado = Decimal(total if total is not None else capital)
            self.servicios_programado = Decimal('0')
            self.otros_programado = Decimal('0')
            saldo = saldo_capital if saldo_capital is not None else '0'
            self.saldo_capital_programado = Decimal(saldo)

    def test_distribuir_excedente_abono_capital(self):
        plan = [
            self.Cuota(1, '833.33', '250.00', total='1083.33', saldo_capital='9166.67'),
            self.Cuota(2, '833.33', '250.00', total='1083.33', saldo_capital='8333.34'),
            self.Cuota(3, '833.34', '250.00', total='1083.34', saldo_capital='7500.00'),
        ]
        lineas = distribuir_cobro_con_excedente_a_capital(plan, 1, Decimal('2000.00'), Decimal('0.00'), {})
        self.assertEqual(len(lineas), 2)
        self.assertEqual(lineas[0]['numero_cuota'], 1)
        self.assertTrue(lineas[1].get('abono_capital'))
        self.assertEqual(lineas[0]['capital'] + lineas[0]['interes'], Decimal('1083.33'))
        self.assertEqual(lineas[1]['capital'], Decimal('916.67'))

    def test_distribuir_excedente_dos_cuotas(self):
        plan = [
            self.Cuota(1, '833.33', '250.00', total='1083.33', saldo_capital='9166.67'),
            self.Cuota(2, '833.33', '250.00', total='1083.33', saldo_capital='8333.34'),
            self.Cuota(3, '833.34', '250.00', total='1083.34', saldo_capital='7500.00'),
        ]
        lineas = distribuir_monto_en_cuotas(plan, 1, Decimal('2000.00'), Decimal('0.00'), {})
        self.assertEqual(len(lineas), 2)
        self.assertEqual(lineas[0]['numero_cuota'], 1)
        self.assertEqual(lineas[1]['numero_cuota'], 2)
        total_aplicado = sum(linea['capital'] + linea['interes'] for linea in lineas)
        self.assertEqual(total_aplicado, Decimal('2000.00'))
        self.assertEqual(lineas[0]['capital'] + lineas[0]['interes'], Decimal('1083.33'))

    def test_saldo_pendiente_con_abono_parcial(self):
        plan = [
            self.Cuota(1, '833.33', '250.00', total='1083.33'),
            self.Cuota(2, '833.33', '250.00', total='1083.33'),
        ]
        abonado = {1: Decimal('1083.33'), 2: Decimal('916.67')}
        self.assertEqual(saldo_pendiente_con_abonos(plan, abonado), Decimal('166.66'))

    def test_pendiente_cuota_parcial(self):
        cuota = self.Cuota(2, '833.33', '250.00', total='1083.33')
        self.assertEqual(pendiente_cuota(cuota, Decimal('916.67')), Decimal('166.66'))


class MovimientosPagoTestCase(SimpleTestCase):
    """Desglose cuota vs abono_capital desde detalle_distribucion."""

    class PagoStub:
        def __init__(self, **kwargs):
            self.id_pago = kwargs.get('id_pago', 1)
            self.fecha_pago = kwargs.get('fecha_pago', date.today())
            self.cobrado_en = kwargs.get('cobrado_en')
            self.documento = kwargs.get('documento')
            self.capital = kwargs.get('capital', Decimal('0'))
            self.interes = kwargs.get('interes', Decimal('0'))
            self.mora = kwargs.get('mora', Decimal('0'))
            self.detalle_distribucion = kwargs.get('detalle_distribucion')
            self.numero_factura = kwargs.get('numero_factura')

    def test_movimientos_separan_cuota_y_abono_capital(self):
        from .core.movimientos_pago import (
            abonado_por_cuota_desde_movimientos,
            abonos_capital_desde_pagos,
            movimientos_desde_pago,
            pago_tiene_varios_movimientos,
        )

        pago = self.PagoStub(
            id_pago=10,
            documento='Cuota 1',
            capital=Decimal('2000.00'),
            interes=Decimal('0.00'),
            detalle_distribucion=[
                {'cuota': 1, 'capital': '1083.33', 'interes': '250.00', 'mora': '0.00', 'total': '1333.33'},
                {'cuota': 2, 'capital': '500.00', 'interes': '166.67', 'mora': '0.00', 'total': '666.67', 'parcial': True},
                {'abono_capital': True, 'capital': '500.00', 'interes': '0.00', 'mora': '0.00', 'total': '500.00'},
            ],
        )
        movs = movimientos_desde_pago(pago)
        self.assertEqual(len(movs), 3)
        self.assertTrue(pago_tiene_varios_movimientos(pago))
        abonado = abonado_por_cuota_desde_movimientos([pago])
        self.assertEqual(abonado[1], Decimal('1333.33'))
        self.assertEqual(abonado[2], Decimal('666.67'))
        abonos = abonos_capital_desde_pagos([pago])
        self.assertEqual(len(abonos), 1)
        self.assertEqual(Decimal(abonos[0]['total']), Decimal('500.00'))

