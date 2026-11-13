#include "deco-theme.hpp"
#include <wayfire/core.hpp>
#include <wayfire/opengl.hpp>
#include <map>
#include <algorithm>
#include <cmath>

namespace wf
{
namespace decor
{
/** Create a new theme with the default parameters */
decoration_theme_t::decoration_theme_t()
{}

/** @return The available height for displaying the title */
int decoration_theme_t::get_title_height() const
{
    return title_height;
}

/** @return The available border for resizing */
int decoration_theme_t::get_border_size() const
{
    return border_size;
}

/** @return The available border for resizing */
void decoration_theme_t::set_buttons(button_type_t flags)
{
    button_flags = flags;
}

/**
 * Fill the given rectangle with the background color(s).
 *
 * @param fb The target framebuffer, must have been bound already
 * @param rectangle The rectangle to redraw.
 * @param scissor The GL scissor rectangle to use.
 * @param active Whether to use active or inactive colors
 */
void decoration_theme_t::update_band(int width, int height, int band, bool active) const
{
    if ((width == band_key_w) && (height == band_key_h) && (band == band_key_band) && (active == band_key_active) &&
        (band_texture.tex != (GLuint)-1))
    {
        return;
    }

    band_key_w = width, band_key_h = height, band_key_band = band, band_key_active = active;
    auto surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, std::max(1, width), std::max(1, band));
    auto cr = cairo_create(surface);
    // Top sheen, as MWX 7 on the web: bright at the edge, fading out by the middle of the title bar.
    auto sheen = cairo_pattern_create_linear(0, 0, 0, 70);
    cairo_pattern_add_color_stop_rgba(sheen, 0, 1, 1, 1, active ? 0.30 : 0.22);
    cairo_pattern_add_color_stop_rgba(sheen, 34.0 / 70, 1, 1, 1, active ? 0.06 : 0.04);
    cairo_pattern_add_color_stop_rgba(sheen, 1, 1, 1, 1, 0);
    cairo_set_source(cr, sheen);
    cairo_paint(cr);
    cairo_pattern_destroy(sheen);
    // Aero's diagonal light streaks: a CSS-style 118° gradient over the whole frame, of which the band shows the top.
    const double th = 118.0 * M_PI / 180.0;
    const double dx = std::sin(th), dy = -std::cos(th);
    const double len = std::abs(width * dx) + std::abs(height * dy);
    const double cx = width / 2.0, cy = height / 2.0;
    auto streaks = cairo_pattern_create_linear(cx - dx * len / 2, cy - dy * len / 2, cx + dx * len / 2, cy + dy * len / 2);
    const double stops[][2] = {{0.22, 0}, {0.225, 0.10}, {0.24, 0.10}, {0.25, 0}, {0.46, 0}, {0.465, 0.07}, {0.50, 0.07},
        {0.51, 0}, {0.70, 0}, {0.705, 0.05}, {0.715, 0.05}, {0.72, 0}};
    for (auto& st : stops)
    {
        cairo_pattern_add_color_stop_rgba(streaks, st[0], 1, 1, 1, st[1] * (active ? 1.0 : 0.6));
    }

    cairo_set_source(cr, streaks);
    cairo_paint(cr);
    cairo_pattern_destroy(streaks);
    cairo_destroy(cr);
    cairo_surface_upload_to_texture(surface, band_texture);
    cairo_surface_destroy(surface);
}

/**
 * Fill the given rectangle with MWX 7's Aero glass: the chosen colour at the chosen intensity over Wayfire's blur, the
 * cached sheen and streaks on the title band, and the frame's rings (a dark outer line, a bright inner one).
 */
void decoration_theme_t::render_background(const wf::render_target_t& fb,
    wf::geometry_t rectangle, const wf::geometry_t& scissor, bool active) const
{
    // Wayfire blends premultiplied colours: multiply by alpha here or translucent fills come out far too bright.
    auto pm = [] (wf::color_t c) { return wf::color_t{c.r * c.a, c.g * c.a, c.b * c.a, c.a}; };
    const wf::color_t c = active_color;
    const int band = (int)border_size + (int)title_height;
    update_band(rectangle.width, rectangle.height, band, active);
    OpenGL::render_begin(fb);
    fb.logic_scissor(scissor);
    const auto proj = fb.get_orthographic_projection();
    if (active)
    {
        OpenGL::render_rectangle(rectangle, pm({c.r, c.g, c.b, c.a}), proj);
    } else
    {
        // Unfocused windows: half the tint and a cool grey veil, so the focused one clearly stands out.
        OpenGL::render_rectangle(rectangle, pm({c.r, c.g, c.b, c.a * 0.5}), proj);
        OpenGL::render_rectangle(rectangle, pm({150 / 255.0, 165 / 255.0, 190 / 255.0, 0.22}), proj);
    }

    OpenGL::render_texture(band_texture.tex, fb, {rectangle.x, rectangle.y, rectangle.width, band},
        glm::vec4(1.0f), OpenGL::TEXTURE_TRANSFORM_INVERT_Y);
    // Rings: outer dark hairline all round, inner bright hairline, and a soft edge where the client area begins.
    const auto r = rectangle;
    const wf::color_t dark = pm({0.0, 20 / 255.0, 60 / 255.0, active ? 0.55 : 0.4});
    const wf::color_t light = pm({1.0, 1.0, 1.0, active ? 0.42 : 0.3});
    OpenGL::render_rectangle({r.x, r.y, r.width, 1}, dark, proj);
    OpenGL::render_rectangle({r.x, r.y + r.height - 1, r.width, 1}, dark, proj);
    OpenGL::render_rectangle({r.x, r.y, 1, r.height}, dark, proj);
    OpenGL::render_rectangle({r.x + r.width - 1, r.y, 1, r.height}, dark, proj);
    OpenGL::render_rectangle({r.x + 1, r.y + 1, r.width - 2, 1}, pm({1.0, 1.0, 1.0, active ? 0.7 : 0.45}), proj);
    OpenGL::render_rectangle({r.x + 1, r.y + r.height - 2, r.width - 2, 1}, light, proj);
    OpenGL::render_rectangle({r.x + 1, r.y + 1, 1, r.height - 2}, light, proj);
    OpenGL::render_rectangle({r.x + r.width - 2, r.y + 1, 1, r.height - 2}, light, proj);
    const int bs = border_size;
    OpenGL::render_rectangle({r.x + bs - 1, r.y + band - 1, r.width - 2 * bs + 2, 1},
        pm({0.05, 0.15, 0.30, 0.35}), proj);
    OpenGL::render_end();
}

/**
 * Render the given text on a cairo_surface_t with the given size.
 * The caller is responsible for freeing the memory afterwards.
 */
cairo_surface_t*decoration_theme_t::render_text(std::string text,
    int width, int height, bool active, const std::string& icon) const
{
    const auto format = CAIRO_FORMAT_ARGB32;
    auto surface = cairo_image_surface_create(format, width, height);

    if (height == 0)
    {
        return surface;
    }

    auto cr = cairo_create(surface);

    // About 13 px at a 24 px title bar, as on the web; the stock plugin fills 80% of the bar.
    const double font_size = std::min(height * 0.5, 15.0 * height / 24.0);

    PangoFontDescription *font_desc = pango_font_description_from_string(((std::string)font).c_str());
    pango_font_description_set_absolute_size(font_desc, font_size * PANGO_SCALE);
    pango_font_description_set_weight(font_desc, PANGO_WEIGHT_SEMIBOLD);

    PangoLayout *layout = pango_cairo_create_layout(cr);
    pango_layout_set_font_description(layout, font_desc);
    pango_layout_set_text(layout, text.c_str(), text.size());
    // The app's icon before the caption, as on the web: about two thirds of the title bar's height.
    double x = 6;
    if (!icon.empty())
    {
        cairo_surface_t *png = cairo_image_surface_create_from_png(icon.c_str());
        if (cairo_surface_status(png) == CAIRO_STATUS_SUCCESS)
        {
            const double side = std::round(height * 0.66);
            const double sc   = side / std::max(1, cairo_image_surface_get_width(png));
            cairo_save(cr);
            cairo_translate(cr, 4, std::round((height - side) / 2.0));
            cairo_scale(cr, sc, sc);
            cairo_set_source_surface(cr, png, 0, 0);
            cairo_pattern_set_filter(cairo_get_source(cr), CAIRO_FILTER_BEST);
            cairo_paint_with_alpha(cr, active ? 1.0 : 0.75);
            cairo_restore(cr);
            x = 4 + side + 6;
        }

        cairo_surface_destroy(png);
    }

    pango_layout_set_width(layout, std::max(0, width - (int)x - 2) * PANGO_SCALE);
    pango_layout_set_ellipsize(layout, PANGO_ELLIPSIZE_END);
    int tw, th;
    pango_layout_get_pixel_size(layout, &tw, &th);
    const double y = (height - th) / 2.0;

    // Caption glow: a white halo keeps dark text readable on any glass tint (MWX 7's "glow plate").
    for (int dx = -1; dx <= 1; dx++)
    {
        for (int dy = -1; dy <= 1; dy++)
        {
            cairo_move_to(cr, x + dx, y + dy);
            cairo_set_source_rgba(cr, 1, 1, 1, (dx == 0 || dy == 0) ? 0.55 : 0.3);
            pango_cairo_show_layout(cr, layout);
        }
    }

    cairo_move_to(cr, x, y);
    if (active)
    {
        cairo_set_source_rgba(cr, 0.04, 0.14, 0.25, 1.0);
    } else
    {
        cairo_set_source_rgba(cr, 0.25, 0.33, 0.42, 0.85);
    }

    pango_cairo_show_layout(cr, layout);
    pango_font_description_free(font_desc);
    g_object_unref(layout);
    cairo_destroy(cr);

    return surface;
}

cairo_surface_t*decoration_theme_t::get_button_surface(button_type_t button,
    const button_state_t& state) const
{
    cairo_surface_t *button_surface = cairo_image_surface_create(
        CAIRO_FORMAT_ARGB32, state.width, state.height);

    auto cr = cairo_create(button_surface);
    cairo_set_antialias(cr, CAIRO_ANTIALIAS_BEST);
    cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);

    // MWX 7 traffic lights: glossy spheres, coloured on the focused window and grey otherwise; the symbol only shows
    // under the pointer. Colours match MWX 7 on the web.
    struct rgb
    {
        double r, g, b;
    };
    rgb light, dark;
    switch (button)
    {
      case BUTTON_CLOSE:
        light = {1.00, 0.45, 0.42}; dark = {0.80, 0.16, 0.13};
        break;

      // As on the web: green minimizes, yellow is Full Screen, red closes.
      case BUTTON_TOGGLE_MAXIMIZE:
        light = {1.00, 0.84, 0.34}; dark = {0.85, 0.58, 0.05};
        break;

      case BUTTON_MINIMIZE:
        light = {0.45, 0.88, 0.36}; dark = {0.13, 0.60, 0.13};
        break;

      default:
        assert(false);
    }

    if (!state.active && fabs(state.hover_progress) < 1e-3)
    {
        light = {0.86, 0.88, 0.91}; dark = {0.62, 0.66, 0.72};
    }

    const double cx = state.width / 2, cy = state.height / 2;
    const double r  = state.width * 0.36;
    // Pressed (negative hover) darkens slightly, hover brightens slightly.
    const double k = state.hover_progress < 0 ? 0.85 : 1.0 + 0.08 * state.hover_progress;

    // Body: radial gradient, light at the bottom (Aqua-style glow), deeper at the rim.
    auto body = cairo_pattern_create_radial(cx, cy + r * 0.55, r * 0.1, cx, cy, r);
    cairo_pattern_add_color_stop_rgb(body, 0.0, std::min(1.0, light.r * k), std::min(1.0, light.g * k),
        std::min(1.0, light.b * k));
    cairo_pattern_add_color_stop_rgb(body, 1.0, dark.r * k, dark.g * k, dark.b * k);
    cairo_arc(cr, cx, cy, r, 0, 2 * M_PI);
    cairo_set_source(cr, body);
    cairo_fill_preserve(cr);
    cairo_pattern_destroy(body);
    // Rim.
    cairo_set_line_width(cr, 1.0);
    cairo_set_source_rgba(cr, dark.r * 0.6, dark.g * 0.6, dark.b * 0.6, 0.8);
    cairo_stroke(cr);

    // Gloss: a white ellipse over the upper half.
    cairo_save(cr);
    cairo_translate(cr, cx, cy - r * 0.42);
    cairo_scale(cr, r * 0.68, r * 0.42);
    auto gloss = cairo_pattern_create_linear(0, -1, 0, 1);
    cairo_pattern_add_color_stop_rgba(gloss, 0.0, 1, 1, 1, 0.95);
    cairo_pattern_add_color_stop_rgba(gloss, 1.0, 1, 1, 1, 0.05);
    cairo_arc(cr, 0, 0, 1, 0, 2 * M_PI);
    cairo_set_source(cr, gloss);
    cairo_fill(cr);
    cairo_pattern_destroy(gloss);
    cairo_restore(cr);

    // Symbols always show (Cosmin's call: clearer than the Mac's hover-only ones); hover makes them stronger.
    {
        const double a = 0.6 + 0.4 * std::min(1.0, fabs(state.hover_progress));
        const double s = r * 0.45;
        cairo_set_source_rgba(cr, 0.25 * dark.r, 0.25 * dark.g, 0.25 * dark.b, 0.85 * a);
        cairo_set_line_width(cr, std::max(1.2, r * 0.18));
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND);
        switch (button)
        {
          case BUTTON_CLOSE:
            cairo_move_to(cr, cx - s, cy - s); cairo_line_to(cr, cx + s, cy + s);
            cairo_move_to(cr, cx + s, cy - s); cairo_line_to(cr, cx - s, cy + s);
            break;

          case BUTTON_TOGGLE_MAXIMIZE:
            // The web's Full Screen glyph: two small corner triangles pointing apart.
            cairo_move_to(cr, cx - s, cy - s); cairo_line_to(cr, cx + s * 0.35, cy - s);
            cairo_line_to(cr, cx - s, cy + s * 0.35); cairo_close_path(cr);
            cairo_move_to(cr, cx + s, cy + s); cairo_line_to(cr, cx - s * 0.35, cy + s);
            cairo_line_to(cr, cx + s, cy - s * 0.35); cairo_close_path(cr);
            cairo_fill(cr);
            break;

          case BUTTON_MINIMIZE:
            cairo_move_to(cr, cx - s, cy); cairo_line_to(cr, cx + s, cy);
            break;

          default:
            break;
        }

        cairo_stroke(cr);
    }

    cairo_destroy(cr);
    return button_surface;
}
}
}
