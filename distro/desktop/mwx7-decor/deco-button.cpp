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
    instant_hover = 0.0;
    update_texture();
    add_idle_damage();
}

bool button_t::fading() const
{
    return (std::string)anim_level == "full";
}

double button_t::hover_value() const
{
    return fading() ? double(hover) : instant_hover;
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
        const double target = is_hovered ? HOVERED : NORMAL;
        if (fading())
        {
            this->hover.animate(target);
        } else
        {
            // No fade: one state change, one damage, and no animation left running to damage every frame.
            instant_hover = target;
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
    const double target = is_pressed ? PRESSED : (is_hovered ? HOVERED : NORMAL);
    if (fading())
    {
        this->hover.animate(target);
    } else
    {
        instant_hover = target;
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
    // The light is drawn on first paint, not on an idle that may run after it: a frame in between showed the title bar
    // without its lights (a missing one until hover).
    if (!current_texture)
    {
        update_texture();
    }

    if (!current_texture)
    {
        return;
    }

    OpenGL::render_begin(fb);
    fb.logic_scissor(scissor);
    OpenGL::render_texture(current_texture->tex, fb, geometry, {1, 1, 1, 1},
        OpenGL::TEXTURE_TRANSFORM_INVERT_Y);
    OpenGL::render_end();

    // running() first: fading() reads an option string, and this runs for every button on every frame of a drag.
    if (this->hover.running() && fading())
    {
        add_idle_damage();
    }
}

void button_t::update_texture()
{
    // Redraw the icon only when it would look different: the hover fade in 12 steps, plus active and type. Drawing
    // with cairo and uploading the texture on every animation frame was the costly part of hovering.
    const int step = (int)std::lround(hover_value() * 12);
    const int key  = theme.get_title_height() * 100000 + step * 64 + (is_active ? 32 : 0) + (int)type % 32;
    if ((key == last_texture_key) && current_texture)
    {
        return;
    }

    last_texture_key = key;
    // The resting looks are drawn at their exact level (as before); only in-between fade frames are rounded to steps.
    const int rest_hovered = (int)std::lround(HOVERED * 12), rest_pressed = (int)std::lround(PRESSED * 12);
    const bool rest = (step == 0) || (step == rest_hovered) || (step == rest_pressed);
    wf::simple_texture_t *target = &fade_texture;
    if (rest)
    {
        auto& slot = rest_textures[key];
        if (slot)
        {
            current_texture = slot.get();
            return;
        }

        slot   = std::make_unique<wf::simple_texture_t>();
        target = slot.get();
    }

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
        .hover_progress = !rest ? hover_value() : step == 0 ? NORMAL : step == rest_hovered ? HOVERED : PRESSED,
        .active = is_active,
    };

    auto surface = theme.get_button_surface(type, state);
    OpenGL::render_begin();
    cairo_surface_upload_to_texture(surface, *target);
    OpenGL::render_end();
    cairo_surface_destroy(surface);
    current_texture = target;
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
