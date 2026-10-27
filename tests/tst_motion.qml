import QtQuick
import QtTest
import "../plugin/DockMotion.js" as Motion
import "fixtures/PreviousMotion.js" as Previous

TestCase {
    name: "DockMotion"

    function test_stationary_data() {
        return [60, 120, 144].map(hz => ({ tag: String(hz), hz: hz }))
    }
    function test_stationary(data) {
        let state = { center: 0, strength: 0 }
        for (let i = 0; i < data.hz; i++) state = Motion.advance(state, 150, 1, 1 / data.hz, false)
        verify(Motion.settled(state, 150, 1, false))
        const first = JSON.stringify(Motion.layout(5, 2, 52, 7, 9, 1.55, state.center, state.strength, 900))
        for (let i = 0; i < data.hz; i++) {
            state = Motion.advance(state, 150, 1, 1 / data.hz, false)
            compare(JSON.stringify(Motion.layout(5, 2, 52, 7, 9, 1.55, state.center, state.strength, 900)), first)
        }
    }
    function test_prompt_response() {
        const tracking = Motion.advance({ center: 0, strength: 1 }, 100, 1, 1 / 60, false)
        verify(tracking.center >= 85, "Tracking must cover at least 85% of a pointer step in its first 60 Hz frame")
        const entry = Motion.advance({ center: 0, strength: 0 }, 100, 1, 1 / 60, false)
        verify(entry.strength >= 0.49, "Hover entry must reach at least 49% strength in its first 60 Hz frame")
    }
    function test_pointer_event_is_immediate() {
        const oldState = { center: 10, strength: 1, dragAge: 0 }
        const next = Motion.track(oldState, 150)
        compare(next.center, 150)
        compare(next.strength, 1)
        compare(oldState.center, 10)
        const entered = Motion.track({ center: 0, strength: 0 }, 90)
        compare(entered.center, 90)
        verify(entered.strength > 0 && entered.strength < 0.25)
    }
    function test_timing() {
        const strengths = [60, 120, 144].map(hz => {
            let state = { center: 0, strength: 0 }
            const frames = Math.round(hz * 0.25)
            for (let i = 0; i < frames; i++) state = Motion.advance(state, 150, 1, 0.25 / frames, false)
            return state.strength
        })
        verify(Math.max(...strengths) - Math.min(...strengths) < 0.000001)
    }
    function test_interruptions() {
        let state = { center: 150, strength: 1 }
        for (let i = 0; i < 120; i++) {
            const x = i % 2 ? 500 : 0
            state = Motion.advance(state, x, i % 7 ? 1 : 0, 1 / 120, false)
            verify(isFinite(state.center) && state.strength >= 0 && state.strength <= 1)
        }
        const before = state.center
        state = Motion.advance(state, 900, 0, 1 / 60, false)
        compare(state.center, before)
        for (let i = 0; i < 90; i++) state = Motion.advance(state, 900, 0, 1 / 60, false)
        compare(state.strength, 0)
        state = Motion.advance(state, 25, 1, 1 / 60, false)
        compare(state.center, 25)
        state = Motion.advance(state, 500, 1, 10, false)
        compare(state.center, 500)
        verify(state.strength >= 0 && state.strength <= 1)
    }
    function test_drag() {
        let state = { center: 150, strength: 1 }
        for (let i = 0; i < 14; i++) state = Motion.advance(state, 500, 0, 1 / 120, true)
        compare(state.strength, 0)
        verify(Motion.settled(state, 500, 0, true))
        state = Motion.advance(state, 30, 1, 1 / 120, false)
        compare(state.center, 30)
        verify(state.strength > 0)
    }
    function test_geometry_data() {
        const rows = []
        for (const width of [320, 768, 1728, 2048])
            for (const size of [32, 52, 96])
                for (const apps of [0, 5, 18]) rows.push({ tag: [width, size, apps].join("/"), width: width, size: size, apps: apps })
        return rows
    }
    function test_geometry(data) {
        const size = Motion.fitSize(data.size, data.apps + 2, data.width)
        const gap = Math.round(size * 0.14), pad = Math.round(size * 0.18)
        const rest = Motion.restWidth(data.apps + 2, size, gap, pad)
        for (const center of [-20, 0, rest / 2, rest, rest + 20]) {
            const layout = Motion.layout(data.apps, 2, size, gap, pad, 2.2, center, 1, data.width)
            verify(layout.left >= 0 && layout.left + layout.width <= data.width + 0.001)
            compare(layout.items.length, data.apps + 3)
            compare(layout.items[data.apps].width, 12)
            for (let i = 0; i < layout.items.length; i++) {
                const item = layout.items[i]
                verify(isFinite(item.x) && item.width >= item.base && item.width <= item.base * 2.2)
                if (i) verify(item.x >= layout.items[i - 1].x + layout.items[i - 1].width)
                if (!item.divider) compare(Motion.hit(layout, layout.left + item.x + item.width / 2, 200 - 10, 200, 8), i)
            }
        }
    }
    function test_crowded_outputs_fit_every_icon() {
        const cases = [{ count: 36, size: 52 }, { count: 400, size: 52 }, { count: 89, size: 52.3 }]
        for (const data of cases) {
            const count = data.count
            const size = Motion.fitSize(data.size, count, 320)
            const gap = Motion.metric(size, 0.14), pad = Motion.metric(size, 0.18)
            verify(size > 0)
            verify(Motion.restWidth(count, size, gap, pad) <= 312)
            const geometry = Motion.layout(Math.floor(count / 2), Math.ceil(count / 2), size, gap, pad, 1.55, 180, 1, 320)
            verify(geometry.left >= 4 && geometry.left + geometry.width <= 316.001)
            for (let i = 0; i < geometry.items.length; i++) {
                const item = geometry.items[i]
                if (item.divider) continue
                const x = geometry.left + item.x + item.width / 2
                compare(Motion.hit(geometry, x, 200 - size / 2, 200, 8), i)
            }
        }
    }
    function test_maximum_magnification_gap_is_continuous() {
        const cases = [
            { apps: 20, minimized: 0, size: 52, gap: 7, pad: 9, viewport: 2000, x: 654.495, step: 0.01, icon: 10 },
            { apps: 5, minimized: 2, size: 32, gap: 4, pad: 6, viewport: 332, x: 288.463, step: 0.001, icon: 6 }
        ]
        for (const data of cases) {
            const before = Motion.layout(data.apps, data.minimized, data.size, data.gap, data.pad, 2.2, data.x, 1, data.viewport)
            const after = Motion.layout(data.apps, data.minimized, data.size, data.gap, data.pad, 2.2, data.x + data.step, 1, data.viewport)
            verify(Math.abs(after.waveCenter - before.waveCenter) < 0.05)
            verify(Math.abs(after.left + after.items[data.icon].x - before.left - before.items[data.icon].x) < 0.05)
        }
    }
    function test_horizontal_sweep_reduces_sideways_movement() {
        const rest = Motion.restWidth(7, 52, 7, 9)
        for (const magnification of [1.55, 2.2]) {
            for (const strength of [0.15, 0.5, 1]) {
                let low = Infinity, high = -Infinity, oldLow = Infinity, oldHigh = -Infinity
                for (let x = -20; x <= rest + 20; x += 4) {
                    const geometry = Motion.layout(5, 2, 52, 7, 9, magnification, x, strength, 1000)
                    const previous = Previous.layout(5, 2, 52, 7, 9, magnification, x, strength, 1000)
                    const middle = geometry.left + geometry.width / 2
                    const oldMiddle = previous.left + previous.width / 2
                    low = Math.min(low, middle); high = Math.max(high, middle)
                    oldLow = Math.min(oldLow, oldMiddle); oldHigh = Math.max(oldHigh, oldMiddle)
                    fuzzyCompare(geometry.left + Motion.mapRest(geometry.items, geometry.waveCenter), (1000 - rest) / 2 + x, 0.005)
                }
                verify(high - low <= (oldHigh - oldLow) * 0.55)
            }
        }
    }
    function test_anchor_and_baseline() {
        for (const strength of [0, 0.2, 0.5, 1]) {
            const geometry = Motion.layout(5, 2, 52, 7, 9, 1.55, 180, strength, 1000)
            fuzzyCompare(geometry.left + Motion.mapRest(geometry.items, geometry.waveCenter), (1000 - geometry.restWidth) / 2 + 180, 0.005)
        }
        const geometry = Motion.layout(5, 0, 52, 7, 9, 1, 180, 1, 1000)
        compare(geometry.width, geometry.restWidth)
        compare(Motion.hit(geometry, 0, 0, 200, 8), -1)
    }
    function test_fitted_metrics_are_continuous() {
        let previous = null
        for (let size = 46; size <= 49; size += 0.001) {
            const geometry = Motion.layout(13, 0, size, Motion.metric(size, 0.14), Motion.metric(size, 0.18), 1.55, 180, 0, 768)
            if (previous) {
                verify(Math.abs(geometry.width - previous.width) < 0.03)
                verify(Math.abs(geometry.left - previous.left) < 0.02)
            }
            previous = geometry
        }
        compare(Motion.metric(52, 0.14), 7)
        compare(Motion.metric(52, 0.18), 9)
    }
}
