// MWX 7 genie: minimize pours the window into its dock icon, restore pours it back out.
// The window is drawn as a stack of thin horizontal strips whose left and right ends follow two S-curves that run
// from the window's edges down to the icon; then the whole window slides down through that funnel.
#pragma once

#include "animate.hpp"
#include <algorithm>
#include <cmath>
#include <vector>
#include <wayfire/opengl.hpp>
#include <wayfire/option-wrapper.hpp>
#include <wayfire/output.hpp>
#include <wayfire/toplevel-view.hpp>
#include <wayfire/view-transform.hpp>
#include <wayfire/util.hpp>

namespace mwx7
{
static const char *genie_vertex_source =
    R"(
#version 100
attribute mediump vec2 position;
attribute mediump vec2 uvPosition;
varying highp vec2 uvpos;
uniform mat4 MVP;

void main() {
    gl_Position = MVP * vec4(position.xy, 0.0, 1.0);
    uvpos = uvPosition;
}
)";

static const char *genie_frag_source =
    R"(
#version 100
@builtin_ext@

varying highp vec2 uvpos;
uniform mediump float alpha;
@builtin@

void main()
{
    gl_FragColor = get_pixel(uvpos) * alpha;
}
)";

inline OpenGL::program_t genie_program;

// Thin strips: at 64 the curve is smooth even on a full-height window.
static constexpr int GENIE_ROWS = 64;

static inline double smooth01(double t)
{
    t = std::clamp(t, 0.0, 1.0);
    return t * t * (3 - 2 * t);
}

class genie_node_t : public wf::scene::transformer_base_node_t
{
  public:
    wlr_box target;
    double progress = 0; // 0 = the window as it is, 1 = fully inside the icon

    genie_node_t(wlr_box target) : transformer_base_node_t(false), target(target)
    {}

    std::string stringify() const override
    {
        return "mwx7-genie";
    }

    wf::geometry_t get_bounding_box() override
    {
        auto box = get_children_bounding_box();
        int x1   = std::min(box.x, target.x), x2 = std::max(box.x + box.width, target.x + target.width);
        int y1   = std::min(box.y, target.y), y2 = std::max(box.y + box.height, target.y + target.height);
        return {x1, y1, x2 - x1, y2 - y1};
    }

    /** Triangles for the current progress, in the same coordinates as the window. */
    void build(std::vector<float>& vert, std::vector<float>& uv)
    {
        auto box = get_children_bounding_box();
        const double x0 = box.x, y0 = box.y, w = box.width, h = box.height;
        const double tl = target.x, tr = target.x + target.width;
        const double ty = target.y + target.height / 2.0;
        // The funnel runs from the window's top edge to the icon. A window that already overlaps the icon still
        // needs a positive run.
        const double run = std::max(ty - y0, 1.0);

        // First the sides bend towards the icon, then the window travels down through them (the two overlap a bit).
        const double bend  = smooth01(progress / 0.45);
        const double slide = smooth01((progress - 0.2) / 0.8);

        auto edge = [&] (double y, double from, double to)
        {
            double f = std::clamp((y - y0) / run, 0.0, 1.0);
            double c = 0.5 - 0.5 * std::cos(M_PI * f);
            return from + (to - from) * c * bend;
        };

        std::vector<float> lx(GENIE_ROWS + 1), rx(GENIE_ROWS + 1), ys(GENIE_ROWS + 1);
        for (int i = 0; i <= GENIE_ROWS; i++)
        {
            double v = 1.0 * i / GENIE_ROWS;
            double y = std::min(y0 + v * h + run * slide, ty);
            ys[i] = y;
            lx[i] = edge(y, x0, tl);
            rx[i] = edge(y, x0 + w, tr);
        }

        auto push = [&] (int i, bool right)
        {
            vert.push_back(right ? rx[i] : lx[i]);
            vert.push_back(ys[i]);
            uv.push_back(right ? 1.0f : 0.0f);
            uv.push_back(1.0f - 1.0f * i / GENIE_ROWS);
        };

        for (int i = 0; i < GENIE_ROWS; i++)
        {
            if (ys[i + 1] - ys[i] < 1e-3)
            {
                continue; // this strip is already inside the icon
            }

            push(i, false);
            push(i + 1, true);
            push(i + 1, false);
            push(i, false);
            push(i, true);
            push(i + 1, true);
        }
    }

    void gen_render_instances(std::vector<wf::scene::render_instance_uptr>& instances,
        wf::scene::damage_callback push_damage, wf::output_t *shown_on) override;
};

class genie_render_instance_t : public wf::scene::transformer_render_instance_t<genie_node_t>
{
  public:
    using transformer_render_instance_t::transformer_render_instance_t;

    void transform_damage_region(wf::region_t& damage) override
    {
        damage |= self->get_bounding_box();
    }

    void render(const wf::render_target_t& target_fb, const wf::region_t& damage) override
    {
        std::vector<float> vert, uv;
        self->build(vert, uv);
        if (vert.empty())
        {
            return;
        }

        auto tex = get_texture(target_fb.scale);
        // The last moments fade, so the window never pops out of existence at the icon.
        float alpha = 1.0f - (float)smooth01((self->progress - 0.85) / 0.15);

        OpenGL::render_begin(target_fb);
        for (auto& box : damage)
        {
            target_fb.logic_scissor(wlr_box_from_pixman_box(box));
            genie_program.use(tex.type);
            genie_program.set_active_texture(tex);
            genie_program.attrib_pointer("position", 2, 0, vert.data());
            genie_program.attrib_pointer("uvPosition", 2, 0, uv.data());
            genie_program.uniformMatrix4f("MVP", target_fb.get_orthographic_projection());
            genie_program.uniform1f("alpha", alpha);
            GL_CALL(glEnable(GL_BLEND));
            GL_CALL(glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA));
            GL_CALL(glDrawArrays(GL_TRIANGLES, 0, vert.size() / 2));
            GL_CALL(glDisable(GL_BLEND));
            genie_program.deactivate();
        }

        OpenGL::render_end();
    }
};

inline void genie_node_t::gen_render_instances(std::vector<wf::scene::render_instance_uptr>& instances,
    wf::scene::damage_callback push_damage, wf::output_t *shown_on)
{
    instances.push_back(std::make_unique<genie_render_instance_t>(this, push_damage, shown_on));
}
}

class genie_animation : public animation_base
{
    wayfire_view view;
    std::shared_ptr<mwx7::genie_node_t> node;
    const std::string name = "mwx7-genie";
    // Driven by the clock rather than a wf duration so a reversal mid-way continues from where the window is.
    uint32_t last = 0;
    int direction = 1; // +1 = into the icon, -1 = out of it
    // 380 ms by default: long enough to read as a pour, short enough to never feel like waiting.
    wf::option_wrapper_t<int> duration{"mwx7-animate/genie_duration"};

  public:
    void init(wayfire_view view, wf::animation_description_t, wf_animation_type type) override
    {
        this->view = view;
        auto toplevel = wf::toplevel_cast(view);
        wlr_box hint  = toplevel ? toplevel->get_minimize_hint() : wlr_box{0, 0, 0, 0};
        if ((hint.width <= 0) || (hint.height <= 0))
        {
            // No dock icon known: pour towards the bottom centre of the screen, where the dock is.
            wf::geometry_t og = view->get_output() ? view->get_output()->get_relative_geometry() :
                wf::geometry_t{0, 0, 1280, 800};
            hint = {og.x + og.width / 2 - 24, og.y + og.height - 60, 48, 48};
        }

        node = std::make_shared<mwx7::genie_node_t>(hint);
        direction = (type & HIDING_ANIMATION) ? 1 : -1;
        node->progress = (direction > 0) ? 0.0 : 1.0;
        last = wf::get_current_time();
        view->get_transformed_node()->add_transformer(node, wf::TRANSFORMER_HIGHLEVEL, name);
    }

    bool step() override
    {
        uint32_t now = wf::get_current_time();
        node->progress = std::clamp(node->progress + direction * double(now - last) / std::max<double>(duration, 50), 0.0, 1.0);
        last = now;
        return direction > 0 ? node->progress < 1.0 : node->progress > 0.0;
    }

    void reverse() override
    {
        direction = -direction;
        last = wf::get_current_time();
    }

    int get_direction() override
    {
        return direction > 0 ? 0 : 1; // HIDDEN : SHOWN, as the stock animations report it
    }

    ~genie_animation()
    {
        view->get_transformed_node()->rem_transformer(name);
    }
};
