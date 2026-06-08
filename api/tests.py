"""Pruebas de la aplicacion API."""
# pylint: disable=no-member

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Cartera, Cliente, HojaCobroImpresion, Pago, Prestamo, PrestamoCuota, Usuario, Zona
from .serializers import PrestamoSerializer


class PrestamoSerializerTestCase(TestCase):
    """Pruebas unitarias para validaciones de PrestamoSerializer."""

    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Cliente Test', dni='0801-2000-00001')
        self.usuario = Usuario.objects.create(
            nombre='Usuario Test',
            rol='asesor',
            correo='asesor@test.com',
            clave='hash-falso',
        )

    def _build_payload(self, **overrides):
        payload = {
            'numero_prestamo': 'PRE-001',
            'id_cliente': self.cliente.id_cliente,
            'id_usuario': self.usuario.id_usuario,
            'monto': Decimal('1500.00'),
            'plazo': 12,
            'tasa_interes': Decimal('25.00'),
            'estado': 'activo',
            'forma_pago': 'mensual',
            'forma_desembolso': 'efectivo',
            'comision': Decimal('0.00'),
            'fecha_entrega': date.today(),
            'fecha_vencimiento': date.today() + timedelta(days=365),
        }
        payload.update(overrides)
        return payload

    def test_rechaza_monto_negativo(self):
        serializer = PrestamoSerializer(data=self._build_payload(monto=Decimal('-1.00')))
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_rechaza_plazo_cero(self):
        serializer = PrestamoSerializer(data=self._build_payload(plazo=0))
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_acepta_prestamo_valido(self):
        serializer = PrestamoSerializer(data=self._build_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)


class RolePermissionIntegrationTestCase(APITestCase):
    """Pruebas de integracion para permisos por rol en endpoints DRF."""

    def setUp(self):
        self.user_model = get_user_model()
        self.cliente_payload = {
            'nombre': 'Cliente API',
            'dni': '0801-2000-00002',
            'telefono': '9999-1111',
        }

    def _auth_with_role(self, role: str, email: str):
        django_user = self.user_model.objects.create_user(
            username=email,
            email=email,
            password='Secreta123!',
        )
        Usuario.objects.create(
            nombre=f'Usuario {role}',
            rol=role,
            correo=email,
            clave='hash-falso',
        )
        self.client.force_authenticate(user=django_user)

    def test_asesor_no_puede_crear_cliente(self):
        self._auth_with_role(role='asesor', email='asesor.permiso@test.com')
        response = self.client.post('/api/v1/clientes/', data=self.cliente_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error']['code'], 'http_403')

    def test_supervisor_si_puede_crear_cliente(self):
        self._auth_with_role(role='supervisor', email='supervisor.permiso@test.com')
        response = self.client.post('/api/v1/clientes/', data=self.cliente_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['nombre'], self.cliente_payload['nombre'])

    def test_asesor_no_puede_crear_cartera(self):
        self._auth_with_role(role='asesor', email='asesor.cartera@test.com')
        response = self.client.post(
            '/api/v1/carteras/',
            data={'nombre': 'Cartera X', 'dia_cobro': 'lunes'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_si_puede_crear_cartera(self):
        self._auth_with_role(role='supervisor', email='supervisor.cartera@test.com')
        payload = {'nombre': 'Cartera Norte', 'dia_cobro': 'lunes'}
        response = self.client.post('/api/v1/carteras/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['nombre'], payload['nombre'])
        self.assertEqual(response.data['dia_cobro'], payload['dia_cobro'])

    def test_supervisor_crear_zona_con_dia_sincroniza_cartera(self):
        self._auth_with_role(role='supervisor', email='supervisor.zona.sync@test.com')
        payload = {'codigo': 'z-sync-1', 'nombre': 'Zona Cobranza Sync', 'dia_semana': 'miercoles'}
        response = self.client.post('/api/v1/zonas/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        zona = Zona.objects.get(codigo='z-sync-1')
        cartera = Cartera.objects.get(zona=zona)
        self.assertEqual(cartera.nombre, zona.nombre)
        self.assertEqual(cartera.dia_cobro, 'miercoles')
        cr = self.client.get(f'/api/v1/carteras/{cartera.id_cartera}/')
        self.assertEqual(cr.status_code, status.HTTP_200_OK)
        self.assertEqual(cr.data.get('id_zona'), zona.id_zona)

    def test_supervisor_actualizar_zona_actualiza_cartera_vinculada(self):
        self._auth_with_role(role='supervisor', email='supervisor.zona.patch@test.com')
        self.client.post(
            '/api/v1/zonas/',
            data={'codigo': 'z-sync-2', 'nombre': 'Zona Vieja', 'dia_semana': 'lunes'},
            format='json',
        )
        zona = Zona.objects.get(codigo='z-sync-2')
        url = f'/api/v1/zonas/{zona.id_zona}/'
        r2 = self.client.patch(url, data={'nombre': 'Zona Nueva', 'dia_semana': 'viernes'}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.data)
        cartera = Cartera.objects.get(zona=zona)
        self.assertEqual(cartera.nombre, 'Zona Nueva')
        self.assertEqual(cartera.dia_cobro, 'viernes')

    def test_supervisor_quitar_dia_zona_elimina_cartera_sincronizada(self):
        self._auth_with_role(role='supervisor', email='supervisor.zona.clear@test.com')
        self.client.post(
            '/api/v1/zonas/',
            data={'codigo': 'z-sync-3', 'nombre': 'Zona Temp', 'dia_semana': 'martes'},
            format='json',
        )
        zona = Zona.objects.get(codigo='z-sync-3')
        self.assertTrue(Cartera.objects.filter(zona=zona).exists())
        url = f'/api/v1/zonas/{zona.id_zona}/'
        r2 = self.client.patch(url, data={'dia_semana': None}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.data)
        self.assertFalse(Cartera.objects.filter(zona=zona).exists())

    def test_supervisor_puede_crear_asesor(self):
        self._auth_with_role(role='supervisor', email='supervisor.alta.asesor@test.com')
        correo = 'nuevo.asesor.api@test.com'
        response = self.client.post(
            '/api/v1/usuarios/',
            data={
                'nombre': 'Asesor API',
                'correo': correo,
                'password': 'TestPass12!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, getattr(response, 'data', response.content))
        self.assertEqual(response.data['rol'], 'asesor')
        self.assertEqual(response.data['correo'], correo)
        self.assertIn('id_usuario', response.data)
        self.assertTrue(Usuario.objects.filter(correo=correo, rol='asesor').exists())

    def test_asesor_no_puede_crear_usuario_operativo(self):
        self._auth_with_role(role='asesor', email='asesor.noalta@test.com')
        response = self.client.post(
            '/api/v1/usuarios/',
            data={
                'nombre': 'Otro',
                'correo': 'otro.asesor@test.com',
                'password': 'TestPass12!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_me_devuelve_perfil_operativo(self):
        self._auth_with_role(role='asesor', email='me.endpoint@test.com')
        response = self.client.get('/api/v1/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['rol'], 'asesor')
        self.assertTrue(response.data['vinculado'])
        self.assertEqual(response.data['email'], 'me.endpoint@test.com')
        op = Usuario.objects.get(correo='me.endpoint@test.com')
        self.assertEqual(response.data['id_usuario'], op.id_usuario)

    def test_simulacion_prestamo_devuelve_cuota_y_tabla(self):
        self._auth_with_role(role='supervisor', email='simulador@test.com')
        payload = {
            'monto': '12000.00',
            'plazo': 12,
            'tasa_interes': '24.00',
            'forma_pago': 'mensual',
            'comision': '1.00',
        }
        response = self.client.post('/api/v1/prestamos/simular/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('cuota_periodica', response.data)
        self.assertIn('total_interes', response.data)
        self.assertIn('total_pagar', response.data)
        self.assertEqual(len(response.data['amortizacion']), 12)

    def test_factura_pdf_pago_retorna_pdf(self):
        self._auth_with_role(role='supervisor', email='pdf.factura@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Factura', dni='0801-2000-00009')
        usuario_operativo = Usuario.objects.get(correo='pdf.factura@test.com')
        prestamo = Prestamo.objects.create(
            numero_prestamo='PRE-FACT-001',
            id_cliente=cliente,
            id_usuario=usuario_operativo,
            monto=Decimal('10000.00'),
            plazo=10,
            tasa_interes=Decimal('12.00'),
            estado='activo',
            forma_pago='mensual',
            forma_desembolso='efectivo',
            comision=Decimal('0.00'),
            fecha_entrega=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=300),
        )
        pago = Pago.objects.create(
            id_prestamo=prestamo,
            fecha_pago=date.today(),
            documento='Cuota 1',
            capital=Decimal('1000.00'),
            interes=Decimal('120.00'),
            mora=Decimal('0.00'),
            saldo=Decimal('9000.00'),
        )

        response = self.client.get(f'/api/v1/pagos/{pago.id_pago}/factura-pdf/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

        response_80 = self.client.get(f'/api/v1/pagos/{pago.id_pago}/factura-pdf/?ticket=80')
        self.assertEqual(response_80.status_code, status.HTTP_200_OK)
        self.assertEqual(response_80['Content-Type'], 'application/pdf')
        self.assertIn('80mm', response_80['Content-Disposition'])

    def test_no_permite_cuota_duplicada_en_mismo_prestamo(self):
        self._auth_with_role(role='supervisor', email='dup.cuota@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Duplicado', dni='0801-2000-00010')
        usuario_operativo = Usuario.objects.get(correo='dup.cuota@test.com')
        prestamo = Prestamo.objects.create(
            numero_prestamo='PRE-DUP-001',
            id_cliente=cliente,
            id_usuario=usuario_operativo,
            monto=Decimal('5000.00'),
            plazo=6,
            tasa_interes=Decimal('10.00'),
            estado='activo',
            forma_pago='mensual',
            forma_desembolso='efectivo',
            comision=Decimal('0.00'),
            fecha_entrega=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=180),
        )
        Pago.objects.create(
            id_prestamo=prestamo,
            fecha_pago=date.today(),
            documento='Cuota 1',
            capital=Decimal('800.00'),
            interes=Decimal('50.00'),
            mora=Decimal('0.00'),
            saldo=Decimal('4200.00'),
        )
        payload = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'CUOTA 1',
            'capital': '800.00',
            'interes': '50.00',
            'mora': '0.00',
            'saldo': '3400.00',
        }
        response = self.client.post('/api/v1/pagos/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_actualiza_estado_prestamo_a_pagado(self):
        self._auth_with_role(role='supervisor', email='estado.prestamo@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Estado', dni='0801-2000-00011')
        usuario_operativo = Usuario.objects.get(correo='estado.prestamo@test.com')
        prestamo = Prestamo.objects.create(
            numero_prestamo='PRE-EST-001',
            id_cliente=cliente,
            id_usuario=usuario_operativo,
            monto=Decimal('3000.00'),
            plazo=3,
            tasa_interes=Decimal('8.00'),
            estado='activo',
            forma_pago='mensual',
            forma_desembolso='efectivo',
            comision=Decimal('0.00'),
            fecha_entrega=date.today() - timedelta(days=90),
            fecha_vencimiento=date.today() + timedelta(days=10),
        )
        payload = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'Cuota 3',
            'capital': '1000.00',
            'interes': '30.00',
            'mora': '0.00',
            'saldo': '0.00',
        }
        response = self.client.post('/api/v1/pagos/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.estado, 'pagado')
        self.assertEqual(prestamo.dias_mora, 0)

    def test_crear_prestamo_genera_plan_cuotas(self):
        """Genera automáticamente cuotas planificadas al crear un préstamo."""
        self._auth_with_role(role='supervisor', email='plan.auto@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Plan Auto', dni='0801-2000-00013')
        usuario_operativo = Usuario.objects.get(correo='plan.auto@test.com')
        payload = {
            'numero_prestamo': 'PRE-AUTO-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'monto': '12000.00',
            'plazo': 12,
            'tasa_interes': '4.00',
            'estado': 'activo',
            'forma_pago': 'mensual',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date.today().isoformat(),
            'fecha_vencimiento': (date.today() + timedelta(days=365)).isoformat(),
        }
        response = self.client.post('/api/v1/prestamos/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        prestamo = Prestamo.objects.get(numero_prestamo='PRE-AUTO-001')
        cuotas = PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota')
        self.assertEqual(cuotas.count(), 12)
        self.assertEqual(cuotas.first().numero_cuota, 1)
        self.assertEqual(cuotas.last().numero_cuota, 12)

    def test_crear_prestamo_semanal_aplica_interes_plano_nominal_dividida_entre_cuatro(self):
        """En semanal usa tasa mensual/4 e interés plano fijo sobre monto original."""
        self._auth_with_role(role='supervisor', email='plan.semanal@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Plan Semanal', dni='0801-2000-00014')
        usuario_operativo = Usuario.objects.get(correo='plan.semanal@test.com')
        payload = {
            'numero_prestamo': 'PRE-AUTO-SEM-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'monto': '12000.00',
            'plazo': 4,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'semanal',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date.today().isoformat(),
            'fecha_vencimiento': (date.today() + timedelta(days=365)).isoformat(),
        }
        response = self.client.post('/api/v1/prestamos/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        prestamo = Prestamo.objects.get(numero_prestamo='PRE-AUTO-SEM-001')
        cuota_1 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=1)
        cuota_2 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=2)
        # 4 meses semanales => 16 cuotas. 10% mensual -> 2.5% semanal; 12000 * 2.5% = 300 fijo.
        self.assertEqual(cuota_1.interes_programado, Decimal('300.00'))
        self.assertEqual(cuota_2.interes_programado, cuota_1.interes_programado)
        self.assertEqual(cuota_1.capital_programado, Decimal('750.00'))
        self.assertEqual(cuota_1.total_programado, Decimal('1050.00'))

    def test_supervisor_puede_crear_cuota_planificada(self):
        """Permite al supervisor crear una cuota planificada manualmente."""
        self._auth_with_role(role='supervisor', email='cuota.plan@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Cuota', dni='0801-2000-00012')
        usuario_operativo = Usuario.objects.get(correo='cuota.plan@test.com')
        prestamo = Prestamo.objects.create(
            numero_prestamo='PRE-CUOTA-001',
            id_cliente=cliente,
            id_usuario=usuario_operativo,
            monto=Decimal('6000.00'),
            plazo=6,
            tasa_interes=Decimal('12.00'),
            estado='activo',
            forma_pago='mensual',
            forma_desembolso='efectivo',
            comision=Decimal('0.00'),
            fecha_entrega=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=180),
        )
        payload = {
            'id_prestamo': prestamo.id_prestamo,
            'numero_cuota': 1,
            'fecha_programada': date.today().isoformat(),
            'capital_programado': '1000.00',
            'interes_programado': '120.00',
            'servicios_programado': '0.00',
            'otros_programado': '0.00',
            'total_programado': '1120.00',
            'saldo_capital_programado': '5000.00',
            'estado': 'pendiente',
        }
        response = self.client.post('/api/v1/prestamo-cuotas/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_registrar_impresion_hoja_cobros_genera_correlativo_persistente(self):
        self._auth_with_role(role='supervisor', email='impresion.hoja@test.com')

        r1 = self.client.post(
            '/api/v1/prestamos/registrar-impresion-hoja-cobros/',
            data={'total_registros': 10},
            format='json',
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.data['numero_impresion'], 1)
        self.assertEqual(r1.data['total_registros'], 10)

        r2 = self.client.post(
            '/api/v1/prestamos/registrar-impresion-hoja-cobros/',
            data={'total_registros': 15},
            format='json',
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.data['numero_impresion'], 2)
        self.assertEqual(r2.data['total_registros'], 15)

        self.assertEqual(HojaCobroImpresion.objects.count(), 2)
