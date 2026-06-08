"""Backfill de hash SHA-256 para documentos de clientes."""

import hashlib

from django.core.management.base import BaseCommand

from api.models import ClienteDocumento


class Command(BaseCommand):
    help = 'Calcula y guarda SHA-256 para documentos existentes sin hash.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recalcula hash para todos los documentos, incluso si ya tienen valor.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=200,
            help='Cantidad de registros a iterar por lote.',
        )

    def handle(self, *args, **options):
        force: bool = options['force']
        batch_size: int = options['batch_size']
        queryset = ClienteDocumento.objects.all().order_by('id_documento')
        if not force:
            queryset = queryset.filter(sha256__isnull=True)

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No hay documentos pendientes de hash.'))
            return

        self.stdout.write(f'Procesando {total} documento(s)...')
        updated = 0
        skipped = 0

        for doc in queryset.iterator(chunk_size=batch_size):
            if not doc.archivo:
                skipped += 1
                self.stdout.write(self.style.WARNING(f'Documento {doc.id_documento} sin archivo; omitido.'))
                continue
            try:
                digest = hashlib.sha256()
                with doc.archivo.open('rb') as file_handle:
                    for chunk in iter(lambda: file_handle.read(1024 * 1024), b''):
                        digest.update(chunk)
                doc.sha256 = digest.hexdigest()
                doc.save(update_fields=['sha256'])
                updated += 1
            except OSError as error:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f'Documento {doc.id_documento} no se pudo leer ({error}); omitido.')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Backfill finalizado. actualizados={updated}, omitidos={skipped}, total={total}'
            )
        )
