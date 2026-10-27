# LumiGo — aplicación web con backend y base de datos (DEMO)

Aplicación experimental con autenticación, roles, SQLite, recargas **ficticias**, marketplace, inventario, generación de QR y pagos con LumiPoints **ficticios**. No maneja pesos ni conexión bancaria. No apta para producción.

## Ejecutar

1. Instala Python 3.10 o superior.
2. Opcional, para imágenes QR escaneables: `python -m pip install qrcode[pil]`.
3. Abre esta carpeta en Visual Studio Code.
4. Ejecuta `python server.py`.
5. Abre **http://localhost:8080** en el mismo computador.

La base de datos `lumigo.sqlite3` se crea al iniciar y preserva usuarios, cobros, compras y puntos entre reinicios. Para restablecer DEMO detén el servidor, elimina `lumigo.sqlite3` y vuelve a arrancar.

## Credenciales demo

| Perfil | Correo | Contraseña |
|---|---|---|
| Usuario | usuario@lumigo.demo | Usuario123! |
| Usuario | carlos@lumigo.demo | Usuario123! |
| Comercio | comercio@lumigo.demo | Comercio123! |
| Operador | operador@lumigo.demo | Operador123! |
| Administrador | admin@lumigo.demo | Admin123! |

## Flujo para probar el QR

1. Inicia sesión como comercio y crea un cobro en `Cobrar QR`.
2. Visualiza el QR (si instalaste la dependencia opcional) o copia la referencia.
3. Cierra sesión e ingresa como usuario.
4. En `Pagar QR` introduce el código o escanea el QR con cámara compatible.
5. Autoriza el pago y comprueba el movimiento.
6. Regresa al comercio para verificar que aparece como pagado.

La cámara en navegador requiere **HTTPS o localhost** y compatibilidad con `BarcodeDetector`. Cuando no esté disponible, se puede introducir el código manualmente.

## Límites y seguridad

- El registro público crea únicamente cuentas de usuario; los perfiles privilegiados son cuentas de demostración preconfiguradas.
- Las contraseñas se derivan con PBKDF2, las sesiones son tokens aleatorios que caducan y los cambios de puntos ocurren en transacciones SQLite con bloqueo.
- La base de datos es **local al servidor**; desde múltiples navegadores contra el mismo servidor comparten saldos y comprobantes.
- El servidor escucha sólo en `127.0.0.1` por seguridad. Para otros dispositivos se necesita despliegue HTTPS con controles de seguridad adicionales.
- No habilitar `0.0.0.0` ni publicar el proyecto como está: faltan protección contra abuso y fuerza bruta, gestión de secretos, MFA, vigilancia, auditoría externa, conciliación financiera, despliegue endurecido y requisitos regulatorios.
- No admite recargas monetarias reales ni redención monetaria. Los LumiPoints transferibles o comprados requieren validación legal especializada en Colombia.
- Los QR contienen una referencia de prueba `LUMIGO-DEMO:<code>`, y **no son QR interoperables bancarios ni Bre-B**.

## Preparación para pruebas por Internet (octubre de 2026)

Esta entrega **no está desplegada**. El servidor incluye un bloqueo para evitar publicar accidentalmente las credenciales conocidas de la demo: al ejecutarse con `HOST=0.0.0.0`, exige `LUMIGO_DEMO_ACCESS_KEY` de al menos 24 caracteres. Para usarlo en un dominio público falta implementar una pantalla de acceso a ese entorno privado o un gateway de autenticación en el hosting; **no publiques el ZIP tal cual**.

Para un despliegue con Render se requiere primero subir el proyecto a un repositorio Git, configurar un servicio web Python, un almacenamiento persistente, HTTPS, credenciales no públicas y controles de acceso. La base SQLite en el filesystem efímero de instancias gratuitas puede perder datos al reiniciarse; usar un almacenamiento persistente o migrar a PostgreSQL.

La API `/api/health` responde sin sesión para comprobaciones del servidor. Sigue siendo exclusivamente una demo con recargas ficticias, QR de prueba y sin integración bancaria.
