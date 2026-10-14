.pragma library

function track(state, pointerX) {
    return { center: pointerX, strength: state.strength === 0 ? 0.15 : state.strength,
        dragAge: state.dragAge, dragStart: state.dragStart }
}

function advance(state, targetX, targetStrength, seconds, dragging) {
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

function settled(state, targetX, targetStrength, dragging) {
    return state.strength === targetStrength && (targetStrength === 0 || state.center === targetX)
        && (!dragging || state.dragAge >= 0.11)
}

function restWidth(count, size, gap, pad) {
    return count * (size + gap) + 12 + pad * 2
}

function metric(size, ratio) {
    // Retain rounded resting metrics without a one-pixel step mid-transition.
    const whole = Math.floor(size)
    const lower = Math.round(whole * ratio)
    return lower + (Math.round((whole + 1) * ratio) - lower) * (size - whole)
}

function fitSize(size, count, viewport) {
    // Fit only this screen; a narrow output must never rewrite his saved size.
    while (size > 8 && restWidth(count, size, Math.round(size * 0.14), Math.round(size * 0.18)) > viewport - 8)
        size -= 1
    return size
}

function slots(apps, minimized, size, gap, pad, magnification, center, strength) {
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

function mapRest(items, coordinate) {
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

function layout(apps, minimized, size, gap, pad, magnification, center, strength, viewport) {
    const resting = restWidth(apps + minimized, size, gap, pad)
    const limit = Math.max(resting, viewport - 8)
    let result = slots(apps, minimized, size, gap, pad, magnification, center, strength)
    if (result.width > limit) {
        // Every icon uses the same constrained amplitude, preserving the wave's shape.
        const factor = (limit - resting) / (result.width - resting)
        result = slots(apps, minimized, size, gap, pad, magnification, center, strength * factor)
    }
    const anchored = (viewport - resting) / 2 + center - mapRest(result.items, center)
    result.left = Math.max(4, Math.min(viewport - result.width - 4, anchored))
    result.restWidth = resting
    return result
}

function hit(layout, x, y, baseline, dotSpace) {
    const local = x - layout.left
    for (let i = 0; i < layout.items.length; i++) {
        const item = layout.items[i]
        if (!item.divider && local >= item.x && local < item.x + item.width
                && y >= baseline - item.width - dotSpace && y <= baseline)
            return i
    }
    return -1
}
