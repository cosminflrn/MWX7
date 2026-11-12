#include <wayfire/per-output-plugin.hpp>
#include <wayfire/view.hpp>
#include <wayfire/workarea.hpp>
#include <wayfire/matcher.hpp>
#include <wayfire/workspace-set.hpp>
#include <wayfire/output.hpp>
#include <wayfire/signal-definitions.hpp>
#include <wayfire/txn/transaction-manager.hpp>

#include "deco-subsurface.hpp"
#include "deco-theme.hpp"
#include <wayfire/plugins/common/shared-core-data.hpp>
#include <wayfire/window-manager.hpp>
#include <wayfire/plugins/ipc/ipc-method-repository.hpp>
#include <wayfire/plugins/ipc/ipc-helpers.hpp>
#include "wayfire/core.hpp"
#include "wayfire/plugin.hpp"
#include "wayfire/signal-provider.hpp"
#include "wayfire/toplevel-view.hpp"
#include "wayfire/toplevel.hpp"
#include <wayfire/opengl.hpp>
#include <cairo.h>
#include <vector>
#include <map>
#include <wayfire/util.hpp>

class wayfire_decoration : public wf::plugin_interface_t
{
    wf::view_matcher_t ignore_views{"decoration/ignore_views"};

    wf::signal::connection_t<wf::txn::new_transaction_signal> on_new_tx =
        [=] (wf::txn::new_transaction_signal *ev)
    {
        // For each transaction, we need to consider what happens with participating views
        for (const auto& obj : ev->tx->get_objects())
        {
            if (auto toplevel = std::dynamic_pointer_cast<wf::toplevel_t>(obj))
            {
                // First check whether the toplevel already has decoration
                // In that case, we should just set the correct margins
                if (auto deco = toplevel->get_data<wf::simple_decorator_t>())
                {
                    toplevel->pending().margins = deco->get_margins(toplevel->pending());
                    continue;
                }

                // Second case: the view is already mapped, or the transaction does not map it.
                // The view is not being decorated, so nothing to do here.
                if (toplevel->current().mapped || !toplevel->pending().mapped)
                {
                    continue;
                }

                // Third case: the transaction will map the toplevel.
                auto view = wf::find_view_for_toplevel(toplevel);
                wf::dassert(view != nullptr, "Mapping a toplevel means there must be a corresponding view!");
                if (should_decorate_view(view))
                {
                    adjust_new_decorations(view);
                }
            }
        }
    };

    wf::signal::connection_t<wf::view_decoration_state_updated_signal> on_decoration_state_changed =
        [=] (wf::view_decoration_state_updated_signal *ev)
    {
        update_view_decoration(ev->view);
    };

    // allows criteria containing maximized or floating check
    wf::signal::connection_t<wf::view_tiled_signal> on_view_tiled =
        [=] (wf::view_tiled_signal *ev)
    {
        update_view_decoration(ev->view);
    };

    wf::shared_data::ref_ptr_t<wf::ipc::method_repository_t> ipc_repo;
    // The shell knows each app's icon (menu entries, MWX 7's own pictures) and hands its PNG to the frame.
    wf::ipc::method_callback ipc_set_icon = [=] (const nlohmann::json& data)
    {
        WFJSON_EXPECT_FIELD(data, "id", number_unsigned);
        WFJSON_EXPECT_FIELD(data, "path", string);
        auto view = wf::ipc::find_view_by_id(data["id"]);
        if (!view)
        {
            return wf::ipc::json_error("view id not found!");
        }

        auto icon = view->get_data_safe<wf::decor::view_icon_t>();
        std::string path = data["path"];
        if (icon->path != path)
        {
            icon->path = path;
            view->damage();
        }

        return wf::ipc::json_ok();
    };

    // The bar's app menu: Full Screen / Exit Full Screen (Wayfire's own IPC has no maximize).
    wf::ipc::method_callback ipc_toggle_maximize = [=] (const nlohmann::json& data)
    {
        WFJSON_EXPECT_FIELD(data, "id", number_unsigned);
        auto view = wf::toplevel_cast(wf::ipc::find_view_by_id(data["id"]));
        if (!view)
        {
            return wf::ipc::json_error("toplevel view id not found!");
        }

        const bool maxed = view->pending_tiled_edges() == wf::TILED_EDGES_ALL;
        wf::get_core().default_wm->tile_request(view, maxed ? 0 : wf::TILED_EDGES_ALL);
        return wf::ipc::json_ok();
    };

    /**
     * Aero Peek thumbnails: the shell asks for a window's picture (minimized ones too) and gets a small PNG. Wayfire
     * renders the window with its frame into a framebuffer; we read it back, scale it down with cairo and save it.
     */
    wf::ipc::method_callback ipc_thumbnail = [=] (const nlohmann::json& data)
    {
        WFJSON_EXPECT_FIELD(data, "id", number_unsigned);
        WFJSON_EXPECT_FIELD(data, "path", string);
        auto view = wf::ipc::find_view_by_id(data["id"]);
        if (!view || !view->get_output())
        {
            return wf::ipc::json_error("view id not found!");
        }

        int max = data.contains("size") && data["size"].is_number_unsigned() ? (int)data["size"] : 200;
        wf::render_target_t fb;
        view->take_snapshot(fb);
        const int w = fb.viewport_width, h = fb.viewport_height;
        if ((w <= 0) || (h <= 0) || (w > 16384) || (h > 16384))
        {
            OpenGL::render_begin();
            fb.release();
            OpenGL::render_end();
            return wf::ipc::json_error("nothing to show");
        }

        std::vector<uint8_t> px((size_t)w * h * 4);
        OpenGL::render_begin();
        GL_CALL(glBindFramebuffer(GL_FRAMEBUFFER, fb.fb));
        GL_CALL(glPixelStorei(GL_PACK_ALIGNMENT, 1));
        GL_CALL(glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, px.data()));
        fb.release();
        OpenGL::render_end();

        // GL rows run bottom-up and RGBA; cairo wants top-down, native-endian ARGB (both premultiplied).
        cairo_surface_t *full = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h);
        unsigned char *dst = cairo_image_surface_get_data(full);
        const int stride = cairo_image_surface_get_stride(full);
        for (int y = 0; y < h; y++)
        {
            const uint8_t *src = px.data() + (size_t)(h - 1 - y) * w * 4;
            uint32_t *row = (uint32_t*)(dst + (size_t)y * stride);
            for (int x = 0; x < w; x++)
            {
                const uint8_t *p = src + x * 4;
                row[x] = ((uint32_t)p[3] << 24) | ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
            }
        }

        cairo_surface_mark_dirty(full);
        const double k = std::min(1.0, (double)max / std::max(w, h));
        const int tw = std::max(1, (int)(w * k)), th = std::max(1, (int)(h * k));
        cairo_surface_t *thumb = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, tw, th);
        cairo_t *cr = cairo_create(thumb);
        cairo_scale(cr, k, k);
        cairo_set_source_surface(cr, full, 0, 0);
        cairo_pattern_set_filter(cairo_get_source(cr), CAIRO_FILTER_GOOD);
        cairo_paint(cr);
        cairo_destroy(cr);
        std::string path = data["path"];
        const bool ok = cairo_surface_write_to_png(thumb, path.c_str()) == CAIRO_STATUS_SUCCESS;
        cairo_surface_destroy(thumb);
        cairo_surface_destroy(full);
        if (!ok)
        {
            return wf::ipc::json_error("could not write the picture");
        }

        auto res = wf::ipc::json_ok();
        res["width"]  = tw;
        res["height"] = th;
        return res;
    };

    /**
     * Aero Shake (Windows 7): shaking a window by its title bar minimizes every other window; shaking it again brings
     * them back. A shake is four quick left-right turns of a moving (not resizing) window within a second.
     */
    struct shake_t
    {
        int dir = 0;
        int last_x = 0;
        std::vector<int64_t> turns;
    };
    std::map<wayfire_toplevel_view, shake_t> shakes;
    std::vector<std::weak_ptr<wf::view_interface_t>> shaken_away;

    wf::signal::connection_t<wf::view_geometry_changed_signal> on_geometry = [=] (wf::view_geometry_changed_signal *ev)
    {
        auto view = ev->view;
        auto now  = view ? view->get_geometry() : wf::geometry_t{};
        if (!view || (now.width != ev->old_geometry.width) || (now.height != ev->old_geometry.height) ||
            view->pending_tiled_edges() || view->minimized)
        {
            return;
        }

        auto& st = shakes[view];
        const int dx = now.x - ev->old_geometry.x;
        if (std::abs(dx) < 6)
        {
            return;
        }

        const int dir = dx > 0 ? 1 : -1;
        const int64_t t = wf::get_current_time();
        if (st.dir && (dir != st.dir))
        {
            st.turns.push_back(t);
        }

        st.dir = dir;
        while (!st.turns.empty() && (t - st.turns.front() > 1000))
        {
            st.turns.erase(st.turns.begin());
        }

        if (st.turns.size() >= 4)
        {
            st.turns.clear();
            shake(view);
        }
    };

    void shake(wayfire_toplevel_view keep)
    {
        bool restored = false;
        for (auto& weak : shaken_away)
        {
            if (auto v = wf::toplevel_cast(weak.lock().get()))
            {
                if (v->minimized)
                {
                    wf::get_core().default_wm->minimize_request(v, false);
                    restored = true;
                }
            }
        }

        shaken_away.clear();
        if (restored)
        {
            wf::get_core().default_wm->focus_raise_view(keep);
            return;
        }

        for (auto& v : wf::get_core().get_all_views())
        {
            auto t = wf::toplevel_cast(v);
            if (t && (t != keep) && t->is_mapped() && !t->minimized && (t->get_output() == keep->get_output()) &&
                (t->role == wf::VIEW_ROLE_TOPLEVEL) && !t->parent)
            {
                shaken_away.push_back(t->weak_from_this());
                wf::get_core().default_wm->minimize_request(t, true);
            }
        }
    }

    wf::signal::connection_t<wf::view_unmapped_signal> on_unmap = [=] (wf::view_unmapped_signal *ev)
    {
        if (auto t = wf::toplevel_cast(ev->view))
        {
            shakes.erase(t);
        }
    };

  public:
    // Settings changes the frame colour by rewriting the config; repaint every frame so it shows at once (otherwise a
    // window kept its old colour until something else redrew it).
    wf::signal::connection_t<wf::reload_config_signal> on_config_reload = [=] (wf::reload_config_signal*)
    {
        for (auto& view : wf::get_core().get_all_views())
        {
            view->damage();
        }
    };

    void init() override
    {
        ipc_repo->register_method("mwx7/set-icon", ipc_set_icon);
        ipc_repo->register_method("mwx7/toggle-maximize", ipc_toggle_maximize);
        ipc_repo->register_method("mwx7/thumbnail", ipc_thumbnail);
        wf::get_core().connect(&on_config_reload);
        wf::get_core().connect(&on_decoration_state_changed);
        wf::get_core().tx_manager->connect(&on_new_tx);
        wf::get_core().connect(&on_view_tiled);
        wf::get_core().connect(&on_geometry);
        wf::get_core().connect(&on_unmap);

        for (auto& view : wf::get_core().get_all_views())
        {
            update_view_decoration(view);
        }
    }

    void fini() override
    {
        ipc_repo->unregister_method("mwx7/set-icon");
        ipc_repo->unregister_method("mwx7/toggle-maximize");
        ipc_repo->unregister_method("mwx7/thumbnail");
        for (auto view : wf::get_core().get_all_views())
        {
            if (auto toplevel = wf::toplevel_cast(view))
            {
                remove_decoration(toplevel);
                wf::get_core().tx_manager->schedule_object(toplevel->toplevel());
            }
        }
    }

    /**
     * Uses view_matcher_t to match whether the given view needs to be
     * ignored for decoration
     *
     * @param view The view to match
     * @return Whether the given view should be decorated?
     */
    bool ignore_decoration_of_view(wayfire_view view)
    {
        return ignore_views.matches(view);
    }

    bool should_decorate_view(wayfire_toplevel_view view)
    {
        return view->should_be_decorated() && !ignore_decoration_of_view(view);
    }

    void adjust_new_decorations(wayfire_toplevel_view view)
    {
        auto toplevel = view->toplevel();

        toplevel->store_data(std::make_unique<wf::simple_decorator_t>(view));
        auto deco     = toplevel->get_data<wf::simple_decorator_t>();
        auto& pending = toplevel->pending();
        pending.margins = deco->get_margins(pending);

        if (!pending.fullscreen && !pending.tiled_edges)
        {
            pending.geometry = wf::expand_geometry_by_margins(pending.geometry, pending.margins);
            if (view->get_output())
            {
                pending.geometry = wf::clamp(pending.geometry, view->get_output()->workarea->get_workarea());
            }
        }
    }

    void remove_decoration(wayfire_toplevel_view view)
    {
        view->toplevel()->erase_data<wf::simple_decorator_t>();
        auto& pending = view->toplevel()->pending();
        if (!pending.fullscreen && !pending.tiled_edges)
        {
            pending.geometry = wf::shrink_geometry_by_margins(pending.geometry, pending.margins);
        }

        pending.margins = {0, 0, 0, 0};
    }

    void update_view_decoration(wayfire_view view)
    {
        if (auto toplevel = wf::toplevel_cast(view))
        {
            if (should_decorate_view(toplevel))
            {
                adjust_new_decorations(toplevel);
            } else
            {
                remove_decoration(toplevel);
            }

            wf::get_core().tx_manager->schedule_object(toplevel->toplevel());
        }
    }
};

DECLARE_WAYFIRE_PLUGIN(wayfire_decoration);
