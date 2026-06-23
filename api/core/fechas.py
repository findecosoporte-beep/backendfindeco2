"""Cálculo de fechas de vencimiento y cuotas programadas."""



import calendar

from datetime import date, timedelta



from .prestamo_calc import periods_from_months



# Convención Python date.weekday(): lunes=0 … domingo=6

DIA_COBRO_WEEKDAY: dict[str, int] = {

    'lunes': 0,

    'martes': 1,

    'miercoles': 2,

    'jueves': 3,

    'viernes': 4,

    'sabado': 5,

    'domingo': 6,

}





def add_months(base_date: date, months: int) -> date:

    """Suma meses preservando día válido dentro del mes destino."""

    month_index = (base_date.month - 1) + months

    year = base_date.year + (month_index // 12)

    month = (month_index % 12) + 1

    day = min(base_date.day, calendar.monthrange(year, month)[1])

    return date(year, month, day)





def weekday_from_dia_cobro(dia_cobro: str | None) -> int | None:

    """Convierte clave de día de cartera al weekday de Python."""

    if not dia_cobro:

        return None

    return DIA_COBRO_WEEKDAY.get(dia_cobro)





def align_weekday_on_or_after(base_date: date, weekday: int) -> date:

    """Primer día de la semana indicada en o después de ``base_date``."""

    days_ahead = (weekday - base_date.weekday()) % 7

    if days_ahead == 0:

        return base_date

    return base_date + timedelta(days=days_ahead)


def primera_fecha_cuota_programada(
    fecha_entrega: date,
    forma_pago: str,
    weekday: int,
) -> date:
    """Primera cuota según día de ruta de la cartera.

    - Entrega el día anterior al cobro (p. ej. domingo antes de lunes): cobro en el día inmediato.
    - Entrega en el día de cobro o después (lunes–sábado): cobro en el día de la semana siguiente.
    """

    dia_antes_cobro = (weekday + 6) % 7
    if fecha_entrega.weekday() == dia_antes_cobro:
        primera = align_weekday_on_or_after(fecha_entrega, weekday)
    else:
        dia_cobro_esta_semana = fecha_entrega - timedelta(
            days=(fecha_entrega.weekday() - weekday) % 7
        )
        primera = dia_cobro_esta_semana + timedelta(days=7)
    if forma_pago == 'quincenal':
        minimo = fecha_entrega + timedelta(days=15)
        if primera < minimo:
            primera = align_weekday_on_or_after(minimo, weekday)
    return primera


def calculate_fecha_cuota(

    fecha_entrega: date,

    periodo: int,

    forma_pago: str,

    dia_cobro: str | None = None,

) -> date:

    """Calcula la fecha programada de cuota según periodicidad.



    Si ``dia_cobro`` está definido, cada cuota cae en ese día de la semana

    (p. ej. lunes para cartera Comayagua), aunque ``fecha_entrega`` sea otro día.

    """

    weekday = weekday_from_dia_cobro(dia_cobro)

    if weekday is None:

        if forma_pago == 'semanal':

            return fecha_entrega + timedelta(days=periodo * 7)

        if forma_pago == 'quincenal':

            return fecha_entrega + timedelta(days=periodo * 15)

        return add_months(fecha_entrega, periodo)



    if forma_pago == 'semanal':

        primera = primera_fecha_cuota_programada(fecha_entrega, forma_pago, weekday)

        return primera + timedelta(days=(periodo - 1) * 7)

    if forma_pago == 'quincenal':

        primera = primera_fecha_cuota_programada(fecha_entrega, forma_pago, weekday)

        return primera + timedelta(days=(periodo - 1) * 14)

    return align_weekday_on_or_after(add_months(fecha_entrega, periodo), weekday)





def calculate_fecha_vencimiento(

    fecha_entrega: date,

    plazo: int,

    forma_pago: str,

    dia_cobro: str | None = None,

) -> date:

    """Calcula fecha de vencimiento (última cuota) usando plazo en meses."""

    if weekday_from_dia_cobro(dia_cobro) is not None:

        periodos = periods_from_months(plazo, forma_pago)

        return calculate_fecha_cuota(fecha_entrega, periodos, forma_pago, dia_cobro)

    if forma_pago == 'semanal':

        return fecha_entrega + timedelta(days=plazo * 4 * 7)

    if forma_pago == 'quincenal':

        return fecha_entrega + timedelta(days=plazo * 2 * 15)

    return add_months(fecha_entrega, plazo)


