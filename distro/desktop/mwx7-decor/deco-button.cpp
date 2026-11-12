#include <cmath>
#include "deco-button.hpp"
#include "deco-theme.hpp"
#include <wayfire/opengl.hpp>
#include <wayfire/plugins/common/cairo-util.hpp>

#define HOVERED  1.0
#define NORMAL   0.0
#define PRESSED -0.7

namespace wf
{
namespace decor
{
button_t::button_t(const decoration_theme_t& t, std::function<void()> damage) :
    theme(t), damage_callback(damage)
{}

void button_t::set_button_type(button_type_t type)
{
    this->type = type;
    this->hover.animate(0, 0);
    update_texture();
    add_idle_damage();
}

button_type_t button_t::get_button_type() const
{
    return this->type;
}

void button_t::set_hover(bool is_hovered)
{
    // Called for every pointer motion over the title bar: only a real change may repaint (each repaint also redoes
    // the blur behind the frame, which made dragging and hovering laggy in VMs).
    if (is_hovered == this->is_hovered)
    {
        return;
    }

    this->is_hovered = is_hovered;
    if (!this->is_pressed)
    {
        if (is_hovered)
        {
            this->hover.animate(HOVERED);
        } else
        {
            this->hover.animate(NORMAL);
        }
    }

    add_idle_damage();
}

/**
 * Set whether the button is pressed or not.
 * Affects appearance.
 */
void button_t::set_pressed(bool is_pressed)
{
    this->is_pressed = is_pressed;
    if (is_pressed)
    {
        this->hover.animate(PRESSED);
    } else
    {
        this->hover.animate(is_hovered ? HOVERED : NORMAL);
    }

    add_idle_damage();
}

void button_t::set_active(bool active)
{
    if (active != is_active)
    {
        is_active = active;
        add_idle_damage();
    }
}

void button_t::render(const wf::render_target_t& fb, wf::geometry_t geometry,
    wf::geometry_t scissor)
{
    OpenGL::render_begin(fb);
    fb.logic_scissor(scissor);
    OpenGL::render_texture(button_texture.tex, fb, geometry, {1, 1, 1, 1},
        OpenGL::TEXTURE_TRANSFORM_INVERT_Y);
    OpenGL::render_end();

    if (this->hover.running())
    {
        add_idle_damage();
    }
}

void button_t::update_texture()
{
    // Redraw the icon only when it would look different: the hover fade in 12 steps, plus active and type. Drawing
    // with cairo and uploading the texture on every animation frame was the costly part of hovering.
    const int key = theme.get_title_height() * 100000 + (int)std::lround(double(hover) * 12) * 64 +
        (is_active ? 32 : 0) + (int)type % 32;
    if ((key == last_texture_key) && (button_texture.tex != (GLuint)-1))
    {
        return;
    }

    last_texture_key = key;
    /**
     * We render at 100% resolution
     * When uploading the texture, this gets scaled
     * to 70% of the titlebar height. Thus we will have
     * a very crisp image
     */
    decoration_theme_t::button_state_t state = {
        .width  = 1.0 * theme.get_title_height(),
        .height = 1.0 * theme.get_title_height(),
        .border = 1.0,
        .hover_progress = hover,
        .active = is_active,
    };

    auto surface = theme.get_button_surface(type, state);
    OpenGL::render_begin();
    cairo_surface_upload_to_texture(surface, this->button_texture);
    OpenGL::render_end();
    cairo_surface_destroy(surface);
}

void button_t::add_idle_damage()
{
    this->idle_damage.run_once([=] ()
    {
        this->damage_callback();
        update_texture();
    });
}
}
}
