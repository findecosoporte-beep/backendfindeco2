"""Crea usuario Django (login JWT) y perfil operativo en tabla `usuarios`."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Usuario


class Command(BaseCommand):
    help = 'Crea o actualiza cuenta de acceso Django y perfil operativo FINDECO.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Correo (username y email en Django).')
        parser.add_argument('--password', required=True, help='Contraseña de acceso (mín. 8 caracteres).')
        parser.add_argument('--nombre', default='Administrador', help='Nombre en tabla usuarios.')
        parser.add_argument(
            '--rol',
            default='administrador',
            choices=[c[0] for c in Usuario.ROL_CHOICES],
            help='Rol operativo FINDECO.',
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Marca is_superuser/is_staff en Django (opcional).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = (options['email'] or '').strip().lower()
        password = options['password'] or ''
        nombre = (options['nombre'] or '').strip()
        rol = options['rol']
        as_superuser = options['superuser']

        if not email:
            raise CommandError('--email es obligatorio.')
        if len(password) < 8:
            raise CommandError('La contraseña debe tener al menos 8 caracteres.')
        if not nombre:
            raise CommandError('--nombre no puede estar vacío.')

        UserModel = get_user_model()
        auth_user = UserModel.objects.filter(email__iexact=email).first()

        if auth_user is None:
            if as_superuser:
                auth_user = UserModel.objects.create_superuser(
                    username=email,
                    email=email,
                    password=password,
                )
                self.stdout.write(self.style.SUCCESS(f'Cuenta Django superuser creada: {email}'))
            else:
                auth_user = UserModel.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                )
                self.stdout.write(self.style.SUCCESS(f'Cuenta Django creada: {email}'))
        else:
            auth_user.username = email
            auth_user.email = email
            auth_user.set_password(password)
            auth_user.is_active = True
            if as_superuser:
                auth_user.is_superuser = True
                auth_user.is_staff = True
            auth_user.save()
            self.stdout.write(self.style.WARNING(f'Cuenta Django actualizada: {email}'))

        operativo = Usuario.objects.filter(correo__iexact=email).first()
        if operativo is None:
            Usuario.objects.create(
                nombre=nombre,
                correo=email,
                rol=rol,
                clave='legacy-operativo',
            )
            self.stdout.write(self.style.SUCCESS(f'Perfil operativo creado: {rol} / {email}'))
        else:
            operativo.nombre = nombre
            operativo.rol = rol
            operativo.save(update_fields=['nombre', 'rol'])
            self.stdout.write(self.style.WARNING(f'Perfil operativo actualizado: {rol} / {email}'))

        self.stdout.write(self.style.SUCCESS('Listo. Inicia sesión en el front con el correo y la contraseña.'))
