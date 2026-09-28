/** 登录页装饰图谱的轻量运动状态；坐标均在 SVG viewBox 内。 */
export interface MotionBody {
  x: number
  y: number
  vx: number
  vy: number
  angle: number
  angularVelocity: number
  scale: number
  baseScale: number
  pulse: number
  pulseSpeed: number
  phase: number
  radius: number
}

export interface MotionBounds {
  width: number
  height: number
}

/** 移动、缩放并让相遇的图谱反弹；调用方限制帧间隔以避免后台恢复后的大跳跃。 */
export function advanceGraphMotion(
  bodies: MotionBody[],
  deltaSeconds: number,
  elapsedSeconds: number,
  bounds: MotionBounds,
): void {
  const dt = Math.max(0, deltaSeconds)
  for (const body of bodies) {
    body.scale = body.baseScale * (1 + body.pulse * Math.sin(elapsedSeconds * body.pulseSpeed + body.phase))
    body.angle += body.angularVelocity * dt
    if (body.angle > 22) {
      body.angle = 22
      body.angularVelocity = -Math.abs(body.angularVelocity)
    } else if (body.angle < -22) {
      body.angle = -22
      body.angularVelocity = Math.abs(body.angularVelocity)
    }
    body.x += body.vx * dt
    body.y += body.vy * dt
  }

  for (let i = 0; i < bodies.length; i++) {
    for (let j = i + 1; j < bodies.length; j++) {
      const first = bodies[i]
      const second = bodies[j]
      const dx = second.x - first.x
      const dy = second.y - first.y
      const distance = Math.hypot(dx, dy)
      const minimum = (first.radius * first.scale + second.radius * second.scale) * 0.9
      if (distance >= minimum) continue

      const nx = distance === 0 ? 1 : dx / distance
      const ny = distance === 0 ? 0 : dy / distance
      const correction = (minimum - distance) / 2
      first.x -= nx * correction
      first.y -= ny * correction
      second.x += nx * correction
      second.y += ny * correction

      const closingSpeed = (first.vx - second.vx) * nx + (first.vy - second.vy) * ny
      if (closingSpeed > 0) {
        first.vx -= closingSpeed * nx
        first.vy -= closingSpeed * ny
        second.vx += closingSpeed * nx
        second.vy += closingSpeed * ny
      }
    }
  }

  for (const body of bodies) {
    const extent = Math.min(body.radius * body.scale, bounds.width / 2, bounds.height / 2)
    if (body.x < extent) {
      body.x = extent
      body.vx = Math.abs(body.vx)
    } else if (body.x > bounds.width - extent) {
      body.x = bounds.width - extent
      body.vx = -Math.abs(body.vx)
    }
    if (body.y < extent) {
      body.y = extent
      body.vy = Math.abs(body.vy)
    } else if (body.y > bounds.height - extent) {
      body.y = bounds.height - extent
      body.vy = -Math.abs(body.vy)
    }
  }
}
