# litreview.org — Rediseño contemporáneo (adaptación de xuemin.org)

**Fecha:** 2026-09-05  
**Estado:** propuesta / implementación  
**Dominio:** litreview.org / ai.litreview.org  
**Repo:** alrobles/litreview-devel

## Objetivo
Actualizar la landing y el sistema de estilos de litreview.org con un lenguaje visual contemporáneo, inspirado en la elegancia editorial de https://www.xuemin.org/, pero **adaptado, no copiado**. Se mantiene la identidad de LitReview, su contenido y toda la funcionalidad existente (navegación, carga dinámica de `data/reviews.json`, formularios, modo oscuro).

## Decisiones de diseño

### Qué tomamos prestado de xuemin.org
- **Tipografía display serif grande** con mucho aire: titulares en serif (Georgia / ui-serif) a ~3.5–5 rem.
- **Fondos degradados orgánicos** tipo “blob” con blur, en tonos aguamarina, cielo, verde lima y ámbar pálido.
- **Navegación flotante minimalista**, centrada, con CTA de acción principal en píldora degradada.
- **Espaciado generoso** y secciones de ancho completo con poco ruido.
- **CTA flotante/burbuja** opcional (adaptado a un botón “Submit” prominente).

### Qué adaptamos a LitReview
- No usamos video de fondo ni assets pesados; todo es CSS puro.
- No hay scroll-hijacking; la página conserva scroll nativo.
- Paleta propia: blanco cálido / carbón para texto; acento degradado aguamarina → lima → ámbar.
- Contenido real del repo: áreas activas, revisiones recientes, metadatos arXiv-style.
- Modo oscuro conservado; los blobs se invierten a tonos saturados más oscuros.

## Paleta y tokens

```css
--bg: #fafaf9;
--bg-hero: #f5f5f4;
--bg-card: #ffffff;
--bg-nav: rgba(250, 250, 249, 0.82);
--text: #1c1917;
--text-muted: #78716c;
--text-faint: #a8a29e;
--border: #e7e5e4;
--accent-teal: #14b8a6;
--accent-sky: #38bdf8;
--accent-lime: #a3e635;
--accent-amber: #fbbf24;
--gradient-hero: radial-gradient(circle at 20% 30%, var(--accent-teal), transparent 45%),
                 radial-gradient(circle at 80% 70%, var(--accent-lime), transparent 45%),
                 radial-gradient(circle at 50% 50%, var(--accent-sky), transparent 45%);
```

Modo oscuro:

```css
--bg: #0a0a0a;
--bg-hero: #111111;
--bg-card: #141414;
--bg-nav: rgba(10, 10, 10, 0.82);
--text: #f5f5f4;
--text-muted: #a8a29e;
--text-faint: #737373;
--border: #262626;
```

## Tipografía
- **Display:** `ui-serif, Georgia, "Times New Roman", serif` (evoca la elegancia de xuemin sin dependencia de CDN).
- **Body:** `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`.
- **Mono:** `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` para IDs arXiv.

## Estructura de la landing (`index.html`)

1. **Nav fijo glassmorphism**
   - Logo `LitReview` a la izquierda.
   - Links: Browse, Submit, About.
   - Botón “Submit” como píldora degradada.
   - Toggle tema (☀️/🌙) en icono limpio.

2. **Hero de pantalla completa**
   - Fondo: degradados borrosos animados (CSS `@keyframes float`).
   - Título serif grande, por ejemplo: *“Read freely. Review boldly.”*
   - Subtítulo: definición del repo.
   - Dos botones: “Browse reviews” (píldora outline) y “Submit a review” (píldora degradada).

3. **Statement**
   - Párrafo central de misión, max-width 42 rem, tipografía legible.

4. **Disciplines / áreas**
   - 3 tarjetas-blob con títulos serif y metáfora visual.
   - Ej: “Ecology & Evolution”, “Computer Science”, “Physics (soon)”.

5. **Recent submissions**
   - Lista limpia de tarjetas con ID, fecha, título, autores, área, badge “AI-assisted”.
   - Enlace “View all →”.

6. **Features / credenciales**
   - 3 columnas: Expert-written, Open formats, Organized by area.

7. **Footer minimal**
   - Contacto, licencia CC BY 4.0, GitHub.

## Otras páginas
- `about.html`, `browse.html`, `submit.html`, `abs.html`, `admin.html` heredan el nuevo `style.css`.
- Se mantiene la estructura HTML actual; solo se actualizan marcas comunes (`.nav`, `.page-title`, `.section-title`, `.card`, `.btn`, `.pill`).
- Se añade una pequeña cabecera de página en las vistas interiores para dar aire.

## Animaciones y accesibilidad
- Transiciones suaves de `background` y `color` para el cambio de tema.
- Efecto `prefers-reduced-motion`: blobs sin animación.
- Focus visible en inputs y botones.
- Sin imágenes externas; todo el decorado es CSS.

## Notas técnicas
- No se añaden dependencias ni CDN; todo se sirve desde `static/`.
- Se reescribe `static/css/style.css` con los nuevos tokens y componentes.
- `static/js/common.js` permanece inalterado.
- Se conservan los nombres de clase existentes para no romper la carga dinámica de `index.html`, `browse.html` ni `abs.html`.

## Verificación
- Servir localmente con `python3 -m http.server` en la raíz del repo.
- Revisar en desktop y mobile (viewport 1024×768 y 375×667).
- Confirmar modo oscuro y carga de `data/reviews.json`.
