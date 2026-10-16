
export function track(state, pointerX) {
    return { center: pointerX, strength: state.strength === 0 ? 0.15 : state.strength,
        dragAge: state.dragAge, dragStart: state.dragStart }
}

export function advance(state, targetX, targetStrength, seconds, dragging) {
    const dt = Math.max(0, Math.min(0.05, seconds))
    let center = state.center
    let strength = state.strength
    let dragAge = dragging ? (state.dragAge || 0) + dt : 0
    const dragStart = dragging && !state.dragAge ? strength : state.dragStart
    if (targetStrength > 0) center = targetX
    if (dragging) strength = (dragStart || 0) * Math.max(0, 1 - dragAge / 0.11)
    else {
        const tau = targetStrength > strength ? 0.024 : 0.075
        strength += (targetStrength - strength) * (1 - Math.exp(-dt / tau))
        if (Math.abs(targetStrength - strength) < 0.001) strength = targetStrength
    }
    return { center: center, strength: strength, dragAge: dragAge, dragStart: dragStart }
}

export function settled(state, targetX, targetStrength, dragging) {
    return state.strength === targetStrength && (targetStrength === 0 || state.center === targetX)
        && (!dragging || state.dragAge >= 0.11)
}

export function restWidth(count, size, gap, pad) {
    return count * (size + gap) + 12 + pad * 2
}

export function metric(size, ratio) {
    // Retain rounded resting metrics without a one-pixel step mid-transition.
    const whole = Math.floor(size)
    const lower = Math.round(whole * ratio)
    return lower + (Math.round((whole + 1) * ratio) - lower) * (size - whole)
}

export function fitSize(size, count, viewport) {
    // Fit only this screen; a narrow output must never rewrite the configured size.
    while (size > 1 && restWidth(count, size, metric(size, 0.14), metric(size, 0.18)) > viewport - 8)
        size -= 1
    // Below one pixel, rounded gaps and padding are zero; reserve the divider
    // and panel margins so crowded outputs never lose their trailing icons.
    return Math.min(size, (viewport - 20) / Math.max(1, count))
}

export function slots(apps, minimized, size, gap, pad, magnification, center, strength) {
    const out = []
    let rest = pad, live = pad
    const reach = size * 2.4
    for (let i = 0; i < apps + minimized + 1; i++) {
        const divider = i === apps
        const base = divider ? 12 : size
        const distance = Math.abs(center - (rest + base / 2))
        const wave = divider || distance >= reach ? 0 : (1 + Math.cos(Math.PI * distance / reach)) / 2
        const width = base * (1 + (magnification - 1) * strength * wave)
        out.push({ x: live, width: width, rest: rest, base: base, divider: divider })
        rest += base + gap
        live += width + gap
    }
    return { items: out, width: live - gap + pad }
}

export function mapRest(items, coordinate) {
    let restEnd = 0, liveEnd = 0
    for (let i = 0; i < items.length; i++) {
        const slot = items[i]
        if (coordinate < slot.rest) return liveEnd + coordinate - restEnd
        if (coordinate <= slot.rest + slot.base)
            return slot.x + (coordinate - slot.rest) * slot.width / slot.base
        restEnd = slot.rest + slot.base
        liveEnd = slot.x + slot.width
    }
    return liveEnd + coordinate - restEnd
}

export function boundedSlots(apps, minimized, size, gap, pad, magnification, center, strength, resting, limit) {
    let result = slots(apps, minimized, size, gap, pad, magnification, center, strength)
    if (result.width > limit) {
        // Every icon uses the same constrained amplitude, preserving the wave's shape.
        const factor = (limit - resting) / (result.width - resting)
        result = slots(apps, minimized, size, gap, pad, magnification, center, strength * factor)
    }
    return result
}

export function layout(apps, minimized, size, gap, pad, magnification, center, strength, viewport) {
    const resting = restWidth(apps + minimized, size, gap, pad)
    // Half anchoring can put three quarters of the growth on one edge. Reserve
    // that room so a viewport clamp cannot undo the stable pointer mapping.
    const limit = resting + Math.max(0, viewport - 8 - resting) * 2 / 3
    const pointer = (viewport - resting) / 2 + center
    let low = center - (limit - resting) / 2
    let high = center + (limit - resting) / 2
    let waveCenter = center
    let result
    // Split the correction to reduce shelf drift without folding the pointer map
    // at high zoom. Solve this event's geometry, avoiding painted-position feedback.
    for (let i = 0; i < 20; i++) {
        waveCenter = (low + high) / 2
        result = boundedSlots(apps, minimized, size, gap, pad, magnification, waveCenter, strength, resting, limit)
        const coordinate = mapRest(result.items, waveCenter)
        const anchored = (viewport - resting) / 2 + waveCenter - coordinate
        const centered = (viewport - result.width) / 2
        result.left = Math.max(4, Math.min(viewport - result.width - 4, (anchored + centered) / 2))
        const mapped = result.left + coordinate
        if (Math.abs(mapped - pointer) < 0.001) break
        if (mapped < pointer) low = waveCenter
        else high = waveCenter
    }
    result.restWidth = resting
    result.waveCenter = waveCenter
    return result
}

export function hit(layout, x, y, baseline, dotSpace) {
    const local = x - layout.left
    for (let i = 0; i < layout.items.length; i++) {
        const item = layout.items[i]
        if (!item.divider && local >= item.x && local < item.x + item.width
                && y >= baseline - item.width - dotSpace && y <= baseline)
            return i
    }
    return -1
}
