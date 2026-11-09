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
void decoration_theme_t::render_background(const wf::render_target_t& fb,
    wf::geometry_t rectangle, const wf::geometry_t& scissor, bool active) const
{
    // MWX 7 glass: the translucent base colour (Wayfire's blur shows through it), a soft white gloss over the upper half
    // of the title bar, and a bright hairline along the top edge, like the frames of MWX 7 on the web.
    // Wayfire blends premultiplied colours: multiply by alpha here or translucent fills come out far too bright.
    auto pm = [] (wf::color_t c) { return wf::color_t{c.r * c.a, c.g * c.a, c.b * c.a, c.a}; };
    wf::color_t color = active ? active_color : inactive_color;
    const int band = (int)border_size + (int)title_height;
    OpenGL::render_begin(fb);
    fb.logic_scissor(scissor);
    const auto proj = fb.get_orthographic_projection();
    OpenGL::render_rectangle(rectangle, pm(color), proj);
    // Two-step gloss: brighter at the very top, fading towards the middle of the title bar.
    wf::geometry_t gloss1{rectangle.x, rectangle.y, rectangle.width, band / 4};
    OpenGL::render_rectangle(gloss1, pm({1.0, 1.0, 1.0, active ? 0.34 : 0.22}), proj);
    wf::geometry_t gloss2{rectangle.x, rectangle.y + band / 4, rectangle.width, band / 4};
    OpenGL::render_rectangle(gloss2, pm({1.0, 1.0, 1.0, active ? 0.18 : 0.12}), proj);
    wf::geometry_t line{rectangle.x, rectangle.y, rectangle.width, 1};
    OpenGL::render_rectangle(line, pm({1.0, 1.0, 1.0, 0.8}), proj);
    wf::geometry_t base{rectangle.x, rectangle.y + band - 1, rectangle.width, 1};
    OpenGL::render_rectangle(base, pm({0.05, 0.15, 0.30, 0.30}), proj);
    OpenGL::render_end();
}

/**
 * Render the given text on a cairo_surface_t with the given size.
 * The caller is responsible for freeing the memory afterwards.
 */
cairo_surface_t*decoration_theme_t::render_text(std::string text,
    int width, int height, bool active) const
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
    pango_layout_set_width(layout, std::max(0, width - 8) * PANGO_SCALE);
    pango_layout_set_ellipsize(layout, PANGO_ELLIPSIZE_END);
    int tw, th;
    pango_layout_get_pixel_size(layout, &tw, &th);
    const double x = 6, y = (height - th) / 2.0;

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

      case BUTTON_TOGGLE_MAXIMIZE:
        light = {0.45, 0.88, 0.36}; dark = {0.13, 0.60, 0.13};
        break;

      case BUTTON_MINIMIZE:
        light = {1.00, 0.84, 0.34}; dark = {0.85, 0.58, 0.05};
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

    // Symbol on hover.
    if (fabs(state.hover_progress) > 1e-3)
    {
        const double a = std::min(1.0, fabs(state.hover_progress));
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
            cairo_move_to(cr, cx - s, cy); cairo_line_to(cr, cx + s, cy);
            cairo_move_to(cr, cx, cy - s); cairo_line_to(cr, cx, cy + s);
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
