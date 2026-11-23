# PRD — iBistro (`ibistro.mx`)

## 1. Resumen Ejecutivo
**iBistro** es una plataforma SaaS B2B2C multi-tenant diseñada para negocios de catering, banquetes y restaurantes con servicio de eventos. Centraliza la captación de clientes mediante un **único número central de WhatsApp (Concierge)** y **micro-landings personalizadas (`ibistro.mx/c/{slug}`)**, mientras provee al proveedor un ERP operativo completo: menú con variantes configurables, escandallos con merma y rendimiento de cocción, multi-almacén (`stock_fisico` vs `stock_comprometido`), inventario temporal de equipo/mantelería, agenda por bloques horarios concurrentes, cotizador PDF, reservaciones y extensión **POS para ventas en sitio**.

---

## 2. Autenticación, Billing y Gobernanza con Nuna
* **Modelo Comercial:** Plan único gestionado en **Nuna** ($580 MXN/mes precio regular, $399 MXN/mes primeros 3 meses, 7 días de prueba gratis).
* **Flujo OAuth2 (Cliente Confidencial sin PKCE):**
  1. Proveedor inicia sesión en Nuna; Nuna redirige a `GET /api/auth/callback?code={auth_code}`.
  2. Backend de iBistro intercambia `code` en `NUNA_TOKEN_URL` usando `client_id` + `client_secret` (`grant_type=authorization_code`).
  3. Nuna devuelve `access_token` (`JWT RS256`). iBistro lo valida contra `NUNA_JWKS_URL` verificando firma RS256 y `aud="ibistro"`.
  4. Datos maestros sincronizados desde Nuna (solo lectura en iBistro): `nuna_org_id`, `business_name`, `rfc`, `address`, `logo_url`, y estatus de suscripción/trial (`has_active_plan`).
* **Webhook en Tiempo Real (`POST /webhooks/nuna`):** Actualiza `has_active_plan` (`True`/`False`) ante eventos de pago, inicio de trial o suspensión.
* **Regla de Bloqueo (`has_active_plan == False`):**
  * El proveedor pierde acceso operativo al dashboard (solo pantalla de "Suscripción inactiva — Ir a Nuna").
  * Su micro-landing `ibistro.mx/c/{slug}` deja de aceptar cotizaciones ("Proveedor no disponible temporalmente").
  * Sale automáticamente del motor de búsqueda del WhatsApp Concierge.

---

## 3. Modelo de Datos Completo (PostgreSQL / SQLModel)

### 3.1 Tenant y Configuración del Proveedor
* **`Tenant`**
  * `id` (UUID, PK), `nuna_org_id` (str, unique, indexed)
  * `slug` (str, unique, indexed — autogenerado desde `business_name` sanitizado, evitando duplicados y `RESERVED_SLUGS`)
  * `business_name` (str — desde Nuna), `rfc` (str — desde Nuna), `address` (str — desde Nuna), `logo_url` (str, nullable — desde Nuna)
  * `category_tags` (JSONB — categorías seleccionadas del catálogo maestro dado de alta por Super Admin: `["Italiana", "Sushi", "Taquiza", "BBQ", ...]`)
  * `min_guests` (int, default 20), `max_guests` (int, default 300)
  * `accepts_cash` (bool, default True), `accepts_transfer` (bool, default True), `transfer_instructions` (Text — Banco, CLABE, Titular)
  * `whatsapp_phone` (str, E.164 ej. `+5213312345678`), `contact_phone` (str, E.164)
  * `show_prices_public` (bool, default True — controla si la micro-landing muestra precios al público)
  * `default_tax_rate` (float, default 0.16 — IVA configurable aplicable en cotizaciones/POS)
  * `deposit_percentage` (float, default 50.0)
  * `waiter_ratio` (int, default 20), `waiter_cost_per_event` (Decimal)
  * `max_concurrent_events_per_slot` (int, default 1 — configurable para empresas con múltiples unidades/equipos)
  * `travel_buffer_minutes` (int, default 60 — tiempo de traslado entre bloques)
  * `has_active_plan` (bool, default False), `is_verified_concierge` (bool, default False), `concierge_priority_score` (int, default 100)
  * `enabled_modules` (JSONB, default `["catering_core", "concierge_bot", "pos_lite"]`)
* **`TenantPhoto`** *(Galería de fotos de la micro-landing)*
  * `id` (UUID, PK), `tenant_id` (FK), `image_url` (str), `caption` (str, nullable), `display_order` (int)
* **`ServiceScheduleSlot`** *(Horarios de atención por día de la semana)*
  * `id` (UUID, PK), `tenant_id` (FK), `day_of_week` (int `0=Lunes`..`6=Domingo`), `start_time` (time), `end_time` (time), `is_active` (bool)
  * *Ejemplo:* Sábado (`5`) con 3 registros: `10:00-12:00`, `14:00-16:00`, `18:00-20:00`.
* **`ServiceCategory`** *(Catálogo global gestionado por Super Admin)*
  * `id` (UUID, PK), `name` (str, unique), `slug` (str, unique), `icon` (str), `is_active` (bool)

### 3.2 Multi-Almacén, Proveedores de Insumos y Escandallos
* **`Supplier`** *(Proveedores de insumos del negocio de catering)*
  * `id` (UUID, PK), `tenant_id` (FK), `name` (str), `contact_name` (str), `phone` (str, E.164), `email` (str, nullable), `notes` (Text, nullable)
* **`Warehouse`** *(Almacenes: Central, Secos, Refrigeración, Unidad Móvil)*
  * `id` (UUID, PK), `tenant_id` (FK), `name` (str), `is_primary` (bool, default False), `location_notes` (str, nullable)
* **`Ingredient`** *(Insumo maestro)*
  * `id` (UUID, PK), `tenant_id` (FK), `supplier_id` (FK -> `Supplier`, nullable)
  * `name` (str), `unit` (enum: `kg` | `lt` | `pz` | `gr` | `ml`)
  * `purchase_price` (Decimal), `sale_price` (Decimal, nullable — si se vende directo en POS/extras)
  * `min_stock` (float), `max_stock` (float)
  * `waste_factor` (float, `0.0 <= x < 0.95` — merma de limpieza)
  * `cooking_yield_factor` (float, `0.10 <= x <= 1.50` — rendimiento post-cocción)
* **`WarehouseStock`** *(Doble estado: Físico vs Comprometido)*
  * `id` (UUID, PK), `warehouse_id` (FK), `ingredient_id` (FK)
  * `physical_stock` (float, default 0.0 — existencia real en anaquel)
  * `committed_stock` (float, default 0.0 — reservado por eventos confirmados pendientes de surtir)
  * *Propiedad calculada:* `available_stock = physical_stock - committed_stock`.
* **`InventoryMovement`** *(Kardex / Trazabilidad de almacén)*
  * `id` (UUID, PK), `tenant_id` (FK), `warehouse_id` (FK), `ingredient_id` (FK), `movement_type` (enum: `PURCHASE_IN` | `COMMIT_RESERVE` | `COMMIT_RELEASE` | `PRODUCTION_OUT` | `POS_SALE_OUT` | `ADJUSTMENT`), `quantity` (float), `reference_id` (UUID, nullable), `created_at` (datetime)

### 3.3 Menú, Variantes de Paquetes y Extras
* **`Recipe`**
  * `id` (UUID, PK), `tenant_id` (FK), `name` (str), `is_sub_recipe` (bool, default False), `portion_size` (float), `portion_unit` (str)
* **`RecipeItem`**
  * `id` (UUID, PK), `recipe_id` (FK), `ingredient_id` (FK, nullable), `sub_recipe_id` (FK -> `Recipe`, nullable), `net_qty_per_portion` (float)
* **`CateringPackage`**
  * `id` (UUID, PK), `tenant_id` (FK), `category_id` (FK -> `ServiceCategory`)
  * `name` (str), `description` (Text), `photo_url` (str, nullable)
  * `base_price_per_guest` (Decimal), `min_guests` (int), `is_active` (bool, default True)
* **`PackageRecipeGroup`** *(Soporte para paquetes configurables: "Elige 3 guisos de proteína y 2 vegetales")*
  * `id` (UUID, PK), `package_id` (FK), `group_name` (str — ej. `"Guisados de Proteína"`, `"Guarniciones"`), `min_choices` (int, default 1), `max_choices` (int, default 1), `is_fixed` (bool — si `True`, vienen incluidos automáticamente sin que el cliente elija)
* **`PackageGroupOption`**
  * `id` (UUID, PK), `group_id` (FK -> `PackageRecipeGroup`), `recipe_id` (FK -> `Recipe`), `portions_per_guest` (float, default 1.0), `extra_price_per_guest` (Decimal, default 0.0)
* **`MenuExtra`** *(Bebidas, aguas frescas, desechables premium, postres extra)*
  * `id` (UUID, PK), `tenant_id` (FK), `name` (str), `ingredient_id` (FK, nullable), `recipe_id` (FK, nullable), `unit_price` (Decimal), `pricing_type` (enum: `PER_GUEST` | `PER_UNIT`), `is_active` (bool)

### 3.4 Equipo, Mantelería y Mobiliario
* **`EquipmentAsset`**
  * `id` (UUID, PK), `tenant_id` (FK), `name` (str), `category` (enum: `Manteleria` | `Mobiliario` | `Loza` | `Calentamiento` | `Cristaleria`), `total_stock` (int), `rental_price_per_unit` (Decimal, default 0.0), `replacement_cost` (Decimal)
* **`PackageEquipmentRule`**
  * `id` (UUID, PK), `package_id` (FK), `asset_id` (FK), `guests_per_unit` (int — ej. 1 chafer cada 25 personas)

### 3.5 Cotizaciones, Reservaciones y POS en Sitio
* **`DeliveryZone`**
  * `id` (UUID, PK), `tenant_id` (FK), `zone_name` (str), `freight_cost` (Decimal)
* **`Lead`**
  * `id` (UUID, PK), `tenant_id` (FK), `full_name` (str), `phone` (str, E.164), `whatsapp_phone` (str, E.164), `email` (str, nullable), `source` (enum: `micro_landing` | `whatsapp_direct` | `whatsapp_concierge` | `manual_dashboard`)
* **`Quote`** *(Cotización negociable y exportable a PDF)*
  * `id` (UUID, PK), `tenant_id` (FK), `lead_id` (FK), `package_id` (FK), `delivery_zone_id` (FK, nullable)
  * `event_date` (date), `slot_id` (FK -> `ServiceScheduleSlot`), `venue_address` (str), `guest_count` (int), `waiters_count` (int)
  * `selected_options_json` (JSONB — variantes elegidas por el cliente dentro de cada `PackageRecipeGroup`)
  * `selected_extras_json` (JSONB — extras y cantidades)
  * `selected_equipment_json` (JSONB — mobiliario adicional con costo)
  * `subtotal` (Decimal), `discount_amount` (Decimal, default 0.0), `tax_amount` (Decimal, default 0.0 — IVA opcional), `total_amount` (Decimal), `estimated_cogs` (Decimal)
  * `status` (enum: `PENDING_REVIEW` | `SENT_TO_CLIENT` | `NEGOTIATING` | `APPROVED` | `REJECTED`), `public_token` (UUID, unique), `special_requests` (Text, nullable), `created_at` (datetime)
* **`Reservation`** *(Se crea al aprobar una `Quote` o manualmente en dashboard)*
  * `id` (UUID, PK), `tenant_id` (FK), `quote_id` (FK, unique, nullable), `customer_name` (str), `customer_phone` (str, E.164), `venue_address` (str)
  * `event_date` (date, indexed), `slot_id` (FK -> `ServiceScheduleSlot`), `guest_count` (int)
  * `total_amount` (Decimal), `paid_amount` (Decimal, default 0.0), `payment_status` (enum: `UNPAID` | `PARTIAL_DEPOSIT` | `PAID_IN_FULL`)
  * `operation_status` (enum: `CONFIRMED` | `IN_PREP` | `COMPLETED` | `CANCELLED`)
  * `special_requests` (Text, nullable), `created_at` (datetime)
* **`PaymentReceipt`** *(Múltiples comprobantes por reservación: anticipo + liquidación)*
  * `id` (UUID, PK), `reservation_id` (FK), `amount` (Decimal), `payment_method` (enum: `TRANSFER` | `CASH` | `CARD`), `receipt_file_url` (str, nullable), `is_verified` (bool, default False), `uploaded_at` (datetime)
* **`POSOrder`** *(Extensión POS para ventas rápidas en sitio / barra / eventos)*
  * `id` (UUID, PK), `tenant_id` (FK), `warehouse_id` (FK), `reservation_id` (FK, nullable — si es venta adicional dentro de un evento), `items_json` (JSONB), `subtotal` (Decimal), `tax_amount` (Decimal), `total_amount` (Decimal), `payment_method` (enum: `CASH` | `CARD` | `TRANSFER`), `created_at` (datetime)

---

## 4. Casos de Uso y Flujos Principales

### Flujo A: Micro-Landing Pública (`ibistro.mx/c/{slug}`)
1. Exhibe logo, nombre, categorías, galería de fotos (`TenantPhoto`), horarios de atención y botón directo `wa.me/{IBISTRO_CONCIERGE_PHONE}?text=Hola%20iBistro,%20me%20interesa%20cotizar%20con%20provider_id:{tenant.id}`.
2. **Calendario y Slots:** Muestra fechas con disponibilidad. Al elegir fecha, HTMX consulta `GET /api/v1/public/{slug}/slots?date=YYYY-MM-DD` y devuelve solo los bloques (`ServiceScheduleSlot`) donde `reservas_confirmadas_en_slot < max_concurrent_events_per_slot`.
3. **Wizard de Cotización:**
   * Paso 1: Categoría de servicio.
   * Paso 2: Número de invitados y selección de paquete + **variantes obligatorias/opcionales** (`PackageRecipeGroup`, ej. elegir 3 proteínas y 2 vegetales) + Extras.
   * Paso 3: Nombre, teléfono, WhatsApp, dirección del evento y peticiones especiales.
   * Paso 4: Muestra desglose estimado **solo si `tenant.show_prices_public == True`**; de lo contrario muestra *"Cotización lista para revisión personalizada"*.
4. Al enviar, guarda `Quote` (`PENDING_REVIEW`), notifica al proveedor por correo y WhatsApp, y muestra enlace `wa.me` con código de seguimiento.

### Flujo B: WhatsApp Directo e Indirecto (1 Solo Número Central de iBistro)
* **WhatsApp Directo (con `provider_id` en el mensaje):** El bot detecta `provider_id:{uuid}` en el texto inicial, carga el contexto exclusivo de ese proveedor (su calendario, slots libres y paquetes) y guía al cliente a cotizar directamente con él.
* **WhatsApp Indirecto (Concierge Marketplace):** Cliente escribe buscando catering sin proveedor específico. El bot captura `categoría`, `fecha`, `slot/horario` e `invitados`, filtra proveedores con `has_active_plan == True` y `is_verified_concierge == True` con disponibilidad en ese slot, y presenta hasta **3 opciones** con sus links prellenados a `/c/{slug}`.
* **Endpoints Expuestos para el Bot (`/api/v1/concierge/...`):**
  * `GET /api/v1/concierge/providers/search`
  * `GET /api/v1/concierge/providers/{provider_id}/availability`
  * `GET /api/v1/concierge/providers/{provider_id}/menu`
  * `POST /api/v1/concierge/quotes`

### Flujo C: Negociación, PDF, Reserva y Doble Almacén
1. Proveedor abre la `Quote` en su dashboard, puede ajustar precios, aplicar **descuento**, activar/desactivar **IVA (`16%`)** y descargar el **PDF profesional** de cotización.
2. Al pulsar **"Aprobar y Convertir a Reservación"**:
   * Crea la `Reservation`.
   * Calcula explosión de insumos con merma y rendimiento (`gross_qty = (net_qty * guests) / (cooking_yield * (1 - waste_factor))`) y suma esa cantidad a `WarehouseStock.committed_stock` (`InventoryMovement: COMMIT_RESERVE`).
   * Reserva el equipo/mantelería en esa fecha y bloque horario.
3. Cuando el evento pasa a `COMPLETED` (o al surtir producción), `committed_stock` se libera y se descuenta de `physical_stock` (`PRODUCTION_OUT`).

### Flujo D: Extensión POS en Sitio (`/dashboard/pos`)
* Pantalla táctil rápida (HTMX + Alpine.js) vinculada a un almacén específico (`Warehouse`).
* Permite cobrar productos/extras/paquetes rápidos en sitio con **Efectivo, Tarjeta o Transferencia**, aplicando IVA opcional y descontando al instante de `physical_stock` (`POS_SALE_OUT`).

---

## 5. Reportes Sugeridos (Dashboard Proveedor & Super Admin)

### Reportes del Proveedor (`/dashboard/reports`)
1. **Rentabilidad Real por Evento (Margen vs Escandallo):** Compara precio cobrado vs. costo real de insumos con merma + meseros + flete.
2. **Explosión de Compras Consolidada:** Lista agrupada por proveedor de insumos (`Supplier`) para todos los eventos confirmados de los próximos 7 días (restando `available_stock` actual en almacén).
3. **Alertas de Reabastecimiento de Almacén:** Insumos donde `physical_stock - committed_stock <= min_stock`.
4. **Ocupación por Día y Bloque Horario:** Heatmap de slots más demandados y detección de cuellos de botella en equipo/mantelería.
5. **Corte de Caja POS y Cobranza de Eventos:** Desglose de ingresos por método de pago (`Efectivo`, `Transferencia`, `Tarjeta`) y saldos pendientes por cobrar de reservas próximas.

### Panel Super Admin (`/admin`)
1. **Control de Categorías Globales:** Alta/edición de categorías de comida (`Italiana`, `Sushi`, `Taquiza`, `BBQ`, etc.).
2. **Aprobación KYC de Proveedores:** Switch `is_verified_concierge` y revisión de suscripción Nuna (`has_active_plan`).
3. **Torre de Control WhatsApp:** Monitor de sesiones del bot, takeover humano para eventos especiales y métricas de leads directos vs. concierge.
4. **Impersonación y Plantillas Maestras:** Entrar como proveedor para soporte y clonar recetas/insumos base.