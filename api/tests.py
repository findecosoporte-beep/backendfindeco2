"""Pruebas de la aplicacion API."""
# pylint: disable=no-member

import os
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Cartera,
    Cliente,
    HojaCobroImpresion,
    Pago,
    Prestamo,
    PrestamoCuota,
    Usuario,
    UsuarioCartera,
    Zona,
)
from .serializers import PrestamoSerializer


class PrestamoSerializerTestCase(TestCase):
    """Pruebas unitarias para validaciones de PrestamoSerializer."""

    def setUp(self):
        self.cliente = Cliente.objects.create(nombre='Cliente Test', dni='0801-2000-00001')
        self.cartera = Cartera.objects.create(nombre='Cartera Test', dia_cobro='lunes')
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
            'id_cartera': self.cartera.id_cartera,
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

    def test_health_endpoint_publico(self):
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ok')

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

    def test_no_permite_cuota_duplicada_cuando_esta_pagada_totalmente(self):
        self._auth_with_role(role='supervisor', email='dup.cuota@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Duplicado', dni='0801-2000-00010')
        cartera = Cartera.objects.create(nombre='Cartera Dup', dia_cobro='martes')
        usuario_operativo = Usuario.objects.get(correo='dup.cuota@test.com')
        payload_prestamo = {
            'numero_prestamo': 'PRE-DUP-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '5000.00',
            'plazo': 6,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'mensual',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date.today().isoformat(),
        }
        response_prestamo = self.client.post('/api/v1/prestamos/', data=payload_prestamo, format='json')
        self.assertEqual(response_prestamo.status_code, status.HTTP_201_CREATED)
        prestamo = Prestamo.objects.get(numero_prestamo='PRE-DUP-001')
        cuota_1 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=1)
        total_cuota_1 = cuota_1.total_programado
        payload_pago = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'Cuota 1',
            'capital': str(cuota_1.capital_programado),
            'interes': str(cuota_1.interes_programado),
            'mora': '0.00',
            'saldo': '0.00',
            'monto_recibido': str(total_cuota_1),
        }
        response_pago = self.client.post('/api/v1/pagos/', data=payload_pago, format='json')
        self.assertEqual(response_pago.status_code, status.HTTP_201_CREATED)

        payload_duplicado = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'CUOTA 1',
            'capital': str(cuota_1.capital_programado),
            'interes': str(cuota_1.interes_programado),
            'mora': '0.00',
            'saldo': '0.00',
        }
        response = self.client.post('/api/v1/pagos/', data=payload_duplicado, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_excedente_distribuye_en_siguientes_cuotas(self):
        """Si el cliente paga de más, se cierra la cuota actual y el resto abona a la siguiente."""
        self._auth_with_role(role='supervisor', email='excedente.cuota@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Excedente', dni='0801-2000-00016')
        cartera = Cartera.objects.create(nombre='Cartera Excedente', dia_cobro='lunes')
        usuario_operativo = Usuario.objects.get(correo='excedente.cuota@test.com')
        payload_prestamo = {
            'numero_prestamo': 'PRE-EXC-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '10000.00',
            'plazo': 3,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'semanal',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date(2026, 6, 21).isoformat(),
        }
        response_prestamo = self.client.post('/api/v1/prestamos/', data=payload_prestamo, format='json')
        self.assertEqual(response_prestamo.status_code, status.HTTP_201_CREATED)
        prestamo = Prestamo.objects.get(numero_prestamo='PRE-EXC-001')
        cuota_1 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=1)
        cuota_2 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=2)

        payload_pago = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'Cuota 1',
            'capital': str(cuota_1.capital_programado),
            'interes': str(cuota_1.interes_programado),
            'mora': '0.00',
            'saldo': '0.00',
            'monto_recibido': '2000.00',
        }
        response = self.client.post('/api/v1/pagos/', data=payload_pago, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('distribucion', response.data)
        self.assertEqual(len(response.data['distribucion']), 2)
        self.assertEqual(response.data['distribucion'][0]['cuota'], 1)
        self.assertEqual(response.data['distribucion'][1]['cuota'], 2)

        pagos = Pago.objects.filter(id_prestamo=prestamo).order_by('id_pago')
        self.assertEqual(pagos.count(), 2)
        self.assertEqual(pagos[0].documento, 'Cuota 1')
        self.assertEqual(pagos[1].documento, 'Cuota 2')

        total_abonado = sum(
            Decimal(p.capital) + Decimal(p.interes) + Decimal(p.mora) for p in pagos
        )
        self.assertEqual(total_abonado, Decimal('2000.00'))
        self.assertEqual(
            Decimal(pagos[0].capital) + Decimal(pagos[0].interes),
            cuota_1.total_programado,
        )

        reporte = self.client.get('/api/v1/prestamos/reporte-integracion/?all=1')
        self.assertEqual(reporte.status_code, status.HTTP_200_OK)
        filas = [f for f in reporte.data['filas'] if f['numero_prestamo'] == 'PRE-EXC-001']
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(Decimal(fila['saldo_inicial']), Decimal('13000.00'))
        self.assertEqual(Decimal(fila['saldo_actual']), Decimal('11000.00'))
        self.assertEqual(fila['cuota_siguiente_numero'], 2)
        pendiente_cuota_2 = cuota_2.total_programado - (
            Decimal(pagos[1].capital) + Decimal(pagos[1].interes)
        )
        self.assertEqual(Decimal(fila['cuota_siguiente_monto']), pendiente_cuota_2)
        self.assertEqual(Decimal(pagos.last().saldo), Decimal('11000.00'))

    def test_pago_parcial_queda_saldo_en_misma_cuota_sin_interes_adicional(self):
        """Si el cliente paga menos que la cuota, se registra el abono y la cuota sigue abierta."""
        self._auth_with_role(role='supervisor', email='parcial.cuota@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Parcial', dni='0801-2000-00024')
        cartera = Cartera.objects.create(nombre='Cartera Parcial', dia_cobro='lunes')
        usuario_operativo = Usuario.objects.get(correo='parcial.cuota@test.com')
        payload_prestamo = {
            'numero_prestamo': 'PRE-PAR-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '5000.00',
            'plazo': 3,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'semanal',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date(2026, 6, 21).isoformat(),
        }
        response_prestamo = self.client.post('/api/v1/prestamos/', data=payload_prestamo, format='json')
        self.assertEqual(response_prestamo.status_code, status.HTTP_201_CREATED)
        prestamo = Prestamo.objects.get(numero_prestamo='PRE-PAR-001')
        cuota_1 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=1)
        abono_parcial = Decimal('500.00')

        payload_pago = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'Cuota 1',
            'capital': str(cuota_1.capital_programado),
            'interes': str(cuota_1.interes_programado),
            'mora': '0.00',
            'saldo': '0.00',
            'monto_recibido': str(abono_parcial),
        }
        response = self.client.post('/api/v1/pagos/', data=payload_pago, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data.get('distribucion', [])), 1)
        self.assertEqual(Decimal(response.data['distribucion'][0]['total']), abono_parcial)

        pago = Pago.objects.get(id_prestamo=prestamo)
        self.assertEqual(Decimal(pago.capital) + Decimal(pago.interes), abono_parcial)
        pendiente_cuota_1 = cuota_1.total_programado - abono_parcial

        reporte = self.client.get(
            f'/api/v1/prestamos/reporte-integracion/?id_prestamo={prestamo.id_prestamo}&all=1'
        )
        self.assertEqual(reporte.status_code, status.HTTP_200_OK)
        fila = reporte.data['filas'][0]
        self.assertEqual(fila['cuota_siguiente_numero'], 1)
        self.assertEqual(Decimal(fila['cuota_siguiente_monto']), pendiente_cuota_1)
        self.assertGreater(Decimal(pago.saldo), Decimal('0.00'))

    def test_historial_pagos_cobros_por_dia(self):
        """Historial de pagos filtrado por fecha de cobro."""
        self._auth_with_role(role='supervisor', email='hist.pagos@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Hist', dni='0801-2000-00025')
        cartera = Cartera.objects.create(nombre='Cartera Hist', dia_cobro='lunes')
        usuario_operativo = Usuario.objects.get(correo='hist.pagos@test.com')
        payload_prestamo = {
            'numero_prestamo': 'PRE-HIST-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '3000.00',
            'plazo': 2,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'mensual',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date(2026, 6, 21).isoformat(),
        }
        self.client.post('/api/v1/prestamos/', data=payload_prestamo, format='json')
        prestamo = Prestamo.objects.get(numero_prestamo='PRE-HIST-001')
        cuota_1 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=1)
        fecha_cobro = date(2026, 6, 22)
        payload_pago = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': fecha_cobro.isoformat(),
            'documento': 'Cuota 1',
            'capital': str(cuota_1.capital_programado),
            'interes': str(cuota_1.interes_programado),
            'mora': '0.00',
            'saldo': '0.00',
            'monto_recibido': str(cuota_1.total_programado),
        }
        self.client.post('/api/v1/pagos/', data=payload_pago, format='json')

        response = self.client.get(
            f'/api/v1/pagos/historial-cobros/?modo=dia&fecha={fecha_cobro.isoformat()}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['resumen']['registros'], 1)
        self.assertEqual(response.data['filas'][0]['numero_prestamo'], 'PRE-HIST-001')
        self.assertEqual(response.data['filas'][0]['nombre_cliente'], 'Cliente Hist')

        vacio = self.client.get('/api/v1/pagos/historial-cobros/?modo=dia&fecha=2020-01-01')
        self.assertEqual(vacio.status_code, status.HTTP_200_OK)
        self.assertEqual(vacio.data['resumen']['registros'], 0)

        excel = self.client.get(
            f'/api/v1/pagos/historial-cobros-excel/?modo=dia&fecha={fecha_cobro.isoformat()}'
        )
        self.assertEqual(excel.status_code, status.HTTP_200_OK)
        self.assertIn(
            'spreadsheetml',
            excel['Content-Type'],
        )
        self.assertTrue(len(excel.content) > 100)

        pdf = self.client.get(
            f'/api/v1/pagos/historial-cobros-pdf/?modo=dia&fecha={fecha_cobro.isoformat()}'
        )
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_reporte_integracion_incluye_pendiente_aprobacion_en_filtro_cobro(self):
        """La hoja de cobros debe listar préstamos nuevos (pendiente_aprobacion), no solo activos."""
        self._auth_with_role(role='supervisor', email='reporte.pendiente@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Pendiente', dni='0801-2000-00023')
        cartera = Cartera.objects.create(nombre='Cartera Pendiente', dia_cobro='lunes')
        usuario_operativo = Usuario.objects.get(correo='reporte.pendiente@test.com')
        payload = {
            'numero_prestamo': 'PRE-PEND-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '4000.00',
            'plazo': 2,
            'tasa_interes': '8.00',
            'estado': 'pendiente_aprobacion',
            'forma_pago': 'mensual',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date.today().isoformat(),
        }
        create_resp = self.client.post('/api/v1/prestamos/', data=payload, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

        solo_activo = self.client.get('/api/v1/prestamos/reporte-integracion/?estado=activo&all=1')
        self.assertEqual(solo_activo.status_code, status.HTTP_200_OK)
        numeros_activo = {f['numero_prestamo'] for f in solo_activo.data['filas']}
        self.assertNotIn('PRE-PEND-001', numeros_activo)

        filtro_cobro = self.client.get(
            '/api/v1/prestamos/reporte-integracion/?estado=activo,pendiente_aprobacion,mora&all=1'
        )
        self.assertEqual(filtro_cobro.status_code, status.HTTP_200_OK)
        numeros_cobro = {f['numero_prestamo'] for f in filtro_cobro.data['filas']}
        self.assertIn('PRE-PEND-001', numeros_cobro)

    def test_supervisor_crea_cobrador_con_carteras(self):
        self._auth_with_role(role='supervisor', email='supervisor.cobrador@test.com')
        cartera_a = Cartera.objects.create(nombre='Comayagua Test', dia_cobro='lunes')
        cartera_b = Cartera.objects.create(nombre='Las Lajas Test', dia_cobro='martes')
        payload = {
            'rol': 'cobrador',
            'nombre': 'Pedro Cobrador',
            'correo': 'pedro.cobrador@test.com',
            'password': 'Secreta123!',
            'carteras': [cartera_a.id_cartera, cartera_b.id_cartera],
        }
        response = self.client.post('/api/v1/usuarios/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['rol'], 'cobrador')
        self.assertEqual(sorted(response.data['carteras']), sorted([cartera_a.id_cartera, cartera_b.id_cartera]))
        usuario = Usuario.objects.get(correo='pedro.cobrador@test.com')
        self.assertEqual(UsuarioCartera.objects.filter(id_usuario=usuario).count(), 2)

    def test_cartera_no_puede_asignarse_a_dos_cobradores(self):
        self._auth_with_role(role='supervisor', email='supervisor.cobrador.dup@test.com')
        cartera = Cartera.objects.create(nombre='Unica Cartera', dia_cobro='viernes')
        ok = self.client.post(
            '/api/v1/usuarios/',
            data={
                'rol': 'cobrador',
                'nombre': 'Cobrador Uno',
                'correo': 'cobrador.uno@test.com',
                'password': 'Secreta123!',
                'carteras': [cartera.id_cartera],
            },
            format='json',
        )
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED)
        dup = self.client.post(
            '/api/v1/usuarios/',
            data={
                'rol': 'cobrador',
                'nombre': 'Cobrador Dos',
                'correo': 'cobrador.dos@test.com',
                'password': 'Secreta123!',
                'carteras': [cartera.id_cartera],
            },
            format='json',
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cobrador_solo_ve_prestamos_de_su_cartera(self):
        self._auth_with_role(role='supervisor', email='supervisor.scope@test.com')
        supervisor = Usuario.objects.get(correo='supervisor.scope@test.com')
        cartera_propia = Cartera.objects.create(nombre='Cartera Propia', dia_cobro='lunes')
        cartera_otra = Cartera.objects.create(nombre='Cartera Ajena', dia_cobro='martes')
        cliente = Cliente.objects.create(nombre='Cliente Scope', dni='0801-2000-00020')
        Prestamo.objects.create(
            numero_prestamo='PRE-SCOPE-1',
            id_cliente=cliente,
            id_usuario=supervisor,
            id_cartera=cartera_propia,
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
        Prestamo.objects.create(
            numero_prestamo='PRE-SCOPE-2',
            id_cliente=cliente,
            id_usuario=supervisor,
            id_cartera=cartera_otra,
            monto=Decimal('3000.00'),
            plazo=3,
            tasa_interes=Decimal('8.00'),
            estado='activo',
            forma_pago='mensual',
            forma_desembolso='efectivo',
            comision=Decimal('0.00'),
            fecha_entrega=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=90),
        )
        cobrador_user = self.user_model.objects.create_user(
            username='maria.cobrador@test.com',
            email='maria.cobrador@test.com',
            password='Secreta123!',
        )
        cobrador = Usuario.objects.create(
            nombre='Maria Cobrador',
            rol='cobrador',
            correo='maria.cobrador@test.com',
            clave='hash',
        )
        UsuarioCartera.objects.create(id_usuario=cobrador, id_cartera=cartera_propia)
        self.client.force_authenticate(user=cobrador_user)
        response = self.client.get('/api/v1/prestamos/?page_size=50')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        numeros = {row['numero_prestamo'] for row in response.data['results']}
        self.assertEqual(numeros, {'PRE-SCOPE-1'})

    def test_cobrador_no_puede_cobrar_prestamo_de_cartera_ajena(self):
        self._auth_with_role(role='supervisor', email='supervisor.cobro.cartera@test.com')
        supervisor = Usuario.objects.get(correo='supervisor.cobro.cartera@test.com')
        cartera_propia = Cartera.objects.create(nombre='Cartera Cobro Propia', dia_cobro='lunes')
        cartera_otra = Cartera.objects.create(nombre='Cartera Cobro Ajena', dia_cobro='martes')
        cliente = Cliente.objects.create(
            nombre='Cliente Cobro Cartera',
            dni='0801-2000-00021',
            dia_cobro_semanal='lunes',
        )
        payload_prestamo = {
            'numero_prestamo': 'PRE-COBRO-AJENO',
            'id_cliente': cliente.id_cliente,
            'id_usuario': supervisor.id_usuario,
            'id_cartera': cartera_otra.id_cartera,
            'monto': '6000.00',
            'plazo': 3,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'semanal',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date.today().isoformat(),
        }
        response_prestamo = self.client.post('/api/v1/prestamos/', data=payload_prestamo, format='json')
        self.assertEqual(response_prestamo.status_code, status.HTTP_201_CREATED)
        prestamo = Prestamo.objects.get(numero_prestamo='PRE-COBRO-AJENO')
        cuota_1 = PrestamoCuota.objects.get(id_prestamo=prestamo, numero_cuota=1)

        cobrador_user = self.user_model.objects.create_user(
            username='cobrador.cartera@test.com',
            email='cobrador.cartera@test.com',
            password='Secreta123!',
        )
        cobrador = Usuario.objects.create(
            nombre='Cobrador Cartera',
            rol='cobrador',
            correo='cobrador.cartera@test.com',
            clave='hash',
        )
        UsuarioCartera.objects.create(id_usuario=cobrador, id_cartera=cartera_propia)
        self.client.force_authenticate(user=cobrador_user)

        payload_pago = {
            'id_prestamo': prestamo.id_prestamo,
            'fecha_pago': date.today().isoformat(),
            'documento': 'Cuota 1',
            'capital': str(cuota_1.capital_programado),
            'interes': str(cuota_1.interes_programado),
            'mora': '0.00',
            'saldo': '0.00',
            'monto_recibido': str(cuota_1.total_programado),
        }
        response = self.client.post('/api/v1/pagos/', data=payload_pago, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cartera', str(response.data).lower())

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
        cartera = Cartera.objects.create(nombre='Cartera Plan Auto', dia_cobro='martes')
        usuario_operativo = Usuario.objects.get(correo='plan.auto@test.com')
        payload = {
            'numero_prestamo': 'PRE-AUTO-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
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

    def test_crear_prestamo_alinea_cuotas_al_dia_de_cartera(self):
        """Las cuotas programadas caen siempre en el día de cobro de la cartera."""
        self._auth_with_role(role='supervisor', email='plan.dia.cartera@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Dia Cartera', dni='0801-2000-00015')
        cartera = Cartera.objects.create(nombre='Comayagua Test', dia_cobro='lunes')
        usuario_operativo = Usuario.objects.get(correo='plan.dia.cartera@test.com')
        fecha_entrega = date(2026, 6, 25)
        payload = {
            'numero_prestamo': 'PRE-DIA-CART-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '5000.00',
            'plazo': 3,
            'tasa_interes': '4.00',
            'estado': 'activo',
            'forma_pago': 'mensual',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': fecha_entrega.isoformat(),
        }
        response = self.client.post('/api/v1/prestamos/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        prestamo = Prestamo.objects.get(numero_prestamo='PRE-DIA-CART-001')
        cuotas = PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota')
        self.assertEqual(cuotas.count(), 3)
        for cuota in cuotas:
            self.assertEqual(cuota.fecha_programada.weekday(), 0)
        self.assertEqual(prestamo.fecha_vencimiento, cuotas.last().fecha_programada)

    def test_crear_prestamo_semanal_desde_domingo_cuota_en_lunes_cartera(self):
        """Desembolso domingo: cuotas semanales en lunes de la cartera."""
        self._auth_with_role(role='supervisor', email='plan.domingo.lunes@test.com')
        cliente = Cliente.objects.create(
            nombre='Cliente Domingo',
            dni='0801-2000-00022',
            dia_cobro_semanal='lunes',
        )
        cartera = Cartera.objects.create(nombre='Comayagua Lunes', dia_cobro='lunes')
        usuario_operativo = Usuario.objects.get(correo='plan.domingo.lunes@test.com')
        payload = {
            'numero_prestamo': 'PRE-DOM-LUN-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
            'monto': '8000.00',
            'plazo': 1,
            'tasa_interes': '10.00',
            'estado': 'activo',
            'forma_pago': 'semanal',
            'forma_desembolso': 'efectivo',
            'comision': '0.00',
            'fecha_entrega': date(2026, 6, 21).isoformat(),
        }
        response = self.client.post('/api/v1/prestamos/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        prestamo = Prestamo.objects.get(numero_prestamo='PRE-DOM-LUN-001')
        cuotas = PrestamoCuota.objects.filter(id_prestamo=prestamo).order_by('numero_cuota')
        self.assertEqual(cuotas.count(), 4)
        self.assertEqual(cuotas.first().fecha_programada, date(2026, 6, 22))
        for cuota in cuotas:
            self.assertEqual(cuota.fecha_programada.weekday(), 0)

    def test_crear_prestamo_semanal_aplica_interes_plano_nominal_dividida_entre_cuatro(self):
        """En semanal usa tasa mensual/4 e interés plano fijo sobre monto original."""
        self._auth_with_role(role='supervisor', email='plan.semanal@test.com')
        cliente = Cliente.objects.create(nombre='Cliente Plan Semanal', dni='0801-2000-00014')
        cartera = Cartera.objects.create(nombre='Cartera Plan Semanal', dia_cobro='miercoles')
        usuario_operativo = Usuario.objects.get(correo='plan.semanal@test.com')
        payload = {
            'numero_prestamo': 'PRE-AUTO-SEM-001',
            'id_cliente': cliente.id_cliente,
            'id_usuario': usuario_operativo.id_usuario,
            'id_cartera': cartera.id_cartera,
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


class JwtAuthTestCase(APITestCase):
    """Login JWT y rechazo de escritura sin token."""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='jwt.auth@test.com',
            email='jwt.auth@test.com',
            password='Secreta123!',
        )
        Usuario.objects.create(
            nombre='Usuario JWT',
            rol='asesor',
            correo='jwt.auth@test.com',
            clave='legacy-operativo',
        )

    def test_jwt_login_valido(self):
        response = self.client.post(
            '/api/v1/token/',
            {'username': 'jwt.auth@test.com', 'password': 'Secreta123!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_jwt_login_invalido(self):
        response = self.client.post(
            '/api/v1/token/',
            {'username': 'jwt.auth@test.com', 'password': 'incorrecta'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_escritura_sin_token_rechazada(self):
        response = self.client.post(
            '/api/v1/clientes/',
            {'nombre': 'Sin Token', 'dni': '0801-2099-00001'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProductionSettingsTestCase(SimpleTestCase):
    """Validaciones de configuración production (Fase 1 plan producción)."""

    def test_production_requiere_secret_key(self):
        env = os.environ.copy()
        env.update(
            {
                'DJANGO_ENV': 'production',
                'DJANGO_SECRET_KEY': '',
                'ALLOWED_HOSTS': 'api.example.com',
                'DJANGO_DEBUG': 'false',
            }
        )
        api_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr + result.stdout)

    def test_check_deploy_production_ok(self):
        env = os.environ.copy()
        env.update(
            {
                'DJANGO_ENV': 'production',
                'DJANGO_SECRET_KEY': 'ci-test-secret-key-not-for-production-use-only-32chars',
                'ALLOWED_HOSTS': 'api.example.com',
                'DJANGO_DEBUG': 'false',
            }
        )
        api_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_admin_desactivado_en_produccion_por_defecto(self):
        env = os.environ.copy()
        env.update(
            {
                'DJANGO_ENV': 'production',
                'DJANGO_SECRET_KEY': 'ci-test-secret-key-not-for-production-use-only-32chars',
                'ALLOWED_HOSTS': 'api.example.com',
                'DJANGO_DEBUG': 'false',
            }
        )
        api_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [
                sys.executable,
                'manage.py',
                'shell',
                '-c',
                'from django.conf import settings; print(settings.DJANGO_ENABLE_ADMIN)',
            ],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn('False', result.stdout)


class OpenApiSettingsTestCase(APITestCase):
    """Swagger solo cuando OPENAPI_ENABLED está activo."""

    @override_settings(OPENAPI_ENABLED=False)
    def test_docs_no_disponibles_sin_openapi(self):
        response = self.client.get('/api/v1/docs/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(OPENAPI_ENABLED=True)
    def test_docs_disponibles_con_openapi(self):
        response = self.client.get('/api/v1/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
