"""Elimina datos operativos de prueba (préstamos, cobros) conservando usuarios y config."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import (
    Cliente,
    ClienteDocumento,
    ContratoPrestamo,
    HistorialPrestamo,
    HojaCobroImpresion,
    Pago,
    Prestamo,
    PrestamoCuota,
    Servicio,
)


class Command(BaseCommand):
    """Vacía préstamos y cobros de prueba; conserva usuarios, carteras y configuración SAR."""

    help = (
        'Vacía préstamos y cobros de prueba. Conserva usuarios, carteras, zonas y config SAR. '
        'Use --incluir-clientes para borrar también clientes y expedientes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Obligatorio: confirma que desea borrar datos.',
        )
        parser.add_argument(
            '--incluir-clientes',
            action='store_true',
            help='También elimina clientes, documentos del expediente e historial por cliente.',
        )
        parser.add_argument(
            '--incluir-hojas-cobro',
            action='store_true',
            help='Elimina el registro de impresiones de hoja de cobros.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options['confirm']:
            raise CommandError(
                'Operación destructiva. Vuelva a ejecutar con --confirm si está seguro.'
            )

        incluir_clientes = options['incluir_clientes']
        incluir_hojas = options['incluir_hojas_cobro']

        resumen: dict[str, int] = {}

        resumen['pagos'] = Pago.objects.count()
        Pago.objects.update(id_pago_factura=None)
        Pago.objects.all().delete()

        resumen['servicios'] = Servicio.objects.count()
        Servicio.objects.all().delete()

        resumen['contratos_prestamo'] = ContratoPrestamo.objects.count()
        ContratoPrestamo.objects.all().delete()

        resumen['cuotas'] = PrestamoCuota.objects.count()
        PrestamoCuota.objects.all().delete()

        resumen['prestamos'] = Prestamo.objects.count()
        Prestamo.objects.all().delete()

        resumen['historial_prestamos'] = HistorialPrestamo.objects.count()
        HistorialPrestamo.objects.all().delete()

        if incluir_hojas:
            resumen['hojas_cobro'] = HojaCobroImpresion.objects.count()
            HojaCobroImpresion.objects.all().delete()

        if incluir_clientes:
            resumen['documentos_cliente'] = ClienteDocumento.objects.count()
            for doc in ClienteDocumento.objects.all().iterator():
                doc.archivo.delete(save=False)
            ClienteDocumento.objects.all().delete()

            resumen['clientes'] = Cliente.objects.count()
            Cliente.objects.all().delete()

        self.stdout.write('Datos de prueba eliminados:')
        for clave, cantidad in resumen.items():
            self.stdout.write(f'  - {clave}: {cantidad}')

        self.stdout.write(
            'Conservados: usuarios, carteras, zonas, configuración SAR y cuentas Django.'
        )
