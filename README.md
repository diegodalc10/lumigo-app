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

Configuración de pruebas privadas en Render: Python, build `pip install -r requirements.txt`, start `python server.py`, HOST=0.0.0.0. Render proporciona PORT. Health check: /api/health.

Configura LUMIGO_GATE_USER y LUMIGO_GATE_PASSWORD (mínimo 24 caracteres) como variables privadas. Nunca incluyas sus valores en Git. La puerta protege la interfaz y las API salvo el health check, que solo informa modo DEMO.

Las cuentas iniciales usan LUMIGO_USER_PASSWORD, LUMIGO_MERCHANT_PASSWORD, LUMIGO_OPERATOR_PASSWORD y LUMIGO_ADMIN_PASSWORD. Si faltan, se generan claves aleatorias que no se muestran. Configura estas variables antes del primer arranque si necesitas acceder a esos roles. Cambiarlas no modifica cuentas ya creadas. Los usuarios también pueden registrarse después de superar la puerta privada.

SQLite es temporal sin un disco persistente: los datos de prueba pueden perderse con reinicios o despliegues. No introduzcas datos personales reales. Recargas, compras y pagos QR solo modifican puntos locales; no hay integraciones de dinero real ni transferencias bancarias.

## Gestión de pruebas por perfil

- Operador y administrador: menú Usuarios para crear cuentas de tipo usuario con nombre, correo único y contraseña de 12 a 256 caracteres. Inician con cero puntos; no permite crear perfiles privilegiados.
- Administrador: menú Eventos para registrar nombre, fecha y hora de Bogotá, lugar y descripción. Los eventos quedan en el listado administrativo; no envían invitaciones ni venden entradas.
- Administrador: menú Recargas para asignar entre 10.000 y 500.000 puntos ficticios a un usuario. Solicita confirmación y guarda referencia, beneficiario, administrador, fecha y observación. Reintentar una misma operación no duplica el saldo. La recarga aparece también en el historial del usuario.
- Las contraseñas no se muestran en listados ni respuestas; se guardan mediante derivación PBKDF2.
- Las tablas nuevas se crean sin borrar las existentes. Sigue aplicando la limitación del almacenamiento temporal de Render.

Pruebas locales: `python -m unittest discover -s tests -v`. Usan una base temporal y claves aleatorias de prueba; no consultan cuentas del despliegue.

## Dashboards por perfil

Inicio muestra seis indicadores, una gráfica diaria, distribución de operaciones, ranking y actividad reciente. Permite filtrar 7, 30 o 90 días, actualizar manualmente y consultar los valores diarios en tabla. Se actualiza cada 30 segundos cuando Inicio está visible. No utiliza servicios de gráficas externos.

- Administrador: usuarios, comercios activos, recargas, consumos, pagos QR, usuarios nuevos y próximos eventos.
- Operador: actividad general, seguimiento de usuarios y operaciones; no recibe los eventos administrativos.
- Comercio: ventas QR y de productos de sus establecimientos, solicitudes pendientes, catálogo, inventario y productos más vendidos.
- Usuario: su saldo, recargas, consumos, compras, pagos y comercios donde ha utilizado puntos.

Los indicadores de saldo y catálogo son actuales; las operaciones se filtran por el período indicado, usando días de Bogotá. Los saldos iniciales no se representan como recargas. No se inventan movimientos para completar las gráficas. Los endpoints calculan el alcance a partir de la sesión, sin aceptar IDs ajenos como filtros.

## Imágenes y edición de productos

- Todas las cuentas: Mi perfil permite añadir, reemplazar y eliminar su fotografía. Las fotos de perfil solo pueden ser leídas por su propia sesión.
- Administrador: Productos permite gestionar la fotografía de cualquier producto.
- Comercio: Productos permite editar nombre y cantidad disponible de sus propios productos, además de sus imágenes. Una cantidad desactualizada se rechaza para evitar sobrescribir ventas recientes.
- Comercio: Mi negocio admite hasta seis fotografías; los usuarios las ven en Negocios.
- JPG, PNG o WebP estáticos, hasta 5 MB y 16 megapíxeles. El servidor valida el contenido, corrige orientación, reduce dimensiones y vuelve a codificar en JPEG sin metadatos EXIF.
- Las imágenes se guardan en SQLite junto a la demo. No se envían a servicios externos. En el plan actual de Render NO son persistentes frente a reinicios/despliegues.
- Las rutas de imágenes requieren la puerta privada y una sesión de aplicación. Una cookie HttpOnly/Secure limitada a lectura de imágenes permite mostrarlas en el navegador, sin autorizar operaciones de modificación.
