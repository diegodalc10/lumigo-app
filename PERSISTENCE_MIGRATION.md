# Publicación pendiente: proteger los datos existentes

Esta rama incorpora catálogo con imágenes, edición de precios, historial de compras y QR, Excel con dashboard y reinicio de vista auditado. Todo sigue siendo simulado.

## Bloqueo de publicación

No redesplegar ni cambiar el plan del servicio existente hasta obtener un respaldo verificado. Render Free pierde la base SQLite y las imágenes locales al reiniciar, desplegar o suspenderse. La versión publicada no tiene el nuevo endpoint de respaldo; desplegarlo primero NO constituye una migración segura. Free tampoco permite Shell. La recuperación del estado actual no está garantizada: primero debe verificarse si existe una copia externa o un mecanismo de recuperación con Render. No sustituir registros faltantes por datos de ejemplo sin autorización explícita.

## Destino propuesto, sujeto a autorización del costo

Servicio de 512 MB: aproximadamente USD 7/mes; disco persistente de 1 GB: USD 0,25/mes, antes de impuestos y consumos adicionales. Verificar precios al contratar. Mantener despliegue automático desactivado durante la migración.

Configurar disco montado en `/var/data` y variables:

- `LUMIGO_DATA_DIR=/var/data`
- `LUMIGO_DB=/var/data/lumigo.sqlite3`
- `LUMIGO_REQUIRE_PERSISTENT=1`
- No activar `LUMIGO_ALLOW_EMPTY_DB` durante una migración.

Conservar las variables privadas existentes en Render; nunca copiarlas al repositorio. La aplicación cancela el inicio si falta el disco o la base requerida.

## Procedimiento después de conseguir el respaldo

1. Detener nuevas operaciones mediante una ventana de mantenimiento acordada. Obtener copia SQLite consistente con su API de backup, no copiar únicamente el archivo principal si usa WAL.
2. Guardar el respaldo fuera del servidor en almacenamiento privado; verificar `PRAGMA integrity_check`, cuentas, saldos, movimientos, compras, cobros y fotos. Excel es una exportación, no reemplaza el respaldo completo.
3. Restaurar el respaldo en el disco persistente con el proceso detenido, antes de iniciar esta versión. No sobrescribir una base activa.
4. Desplegar esta rama; comprobar login privado, todos los perfiles y coincidencia de conteos y saldos. La migración de esquema no elimina registros. Los nombres históricos anteriores a esta versión se rellenan con el catálogo disponible; no es posible reconstruir nombres ya modificados.
5. Verificar que una operación simulada y una fotografía de prueba sobrevivan a un reinicio controlado. Mantener la copia anterior hasta completar la validación.
6. Programar respaldos privados externos periódicos y comprobar restauraciones. Esta rama ofrece descarga manual de respaldo al administrador; no configura copias externas automáticas. Los snapshots del disco no sustituyen un respaldo SQLite consistente.

## Uso de las nuevas opciones

- Usuarios: Comercios muestra fotografías y productos; Compras incluye compras y pagos QR.
- Comercios: Productos permite nombre, precio, cantidad e imagen; Ventas incluye operaciones completas.
- Inicio/Reportes: Excel con dashboard del período seleccionado y todo el historial autorizado, incluso el oculto por reinicio.
- Reportes: el comercio reinicia su propia vista; el administrador puede reiniciar la vista de un usuario o comercio. Se exige escribir REINICIAR VISTA y confirmar. No borra cuentas, imágenes, productos, saldos ni movimientos.
- Administrador: respaldo privado de SQLite, incluidas fotografías. Contiene datos personales y hashes de contraseña; se excluyen sesiones. No publicarlo ni compartirlo como reporte.

Documentación: https://render.com/docs/free y https://render.com/docs/disks
