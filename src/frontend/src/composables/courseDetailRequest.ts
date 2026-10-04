import type { Course, CoursesApi } from '../api/courses'

// 外壳和课程页共用同代课程作用域的在途读取，既不重复请求，也不缓存旧权限。
const inFlight = new WeakMap<CoursesApi, WeakMap<AbortSignal, Map<string, Promise<Course>>>>()
export function readCourseDetail(api: CoursesApi, cid: string, signal: AbortSignal): Promise<Course> {
  let scopes = inFlight.get(api)
  if (!scopes) { scopes = new WeakMap(); inFlight.set(api, scopes) }
  let courses = scopes.get(signal)
  if (!courses) { courses = new Map(); scopes.set(signal, courses) }
  const current = courses.get(cid)
  if (current) return current
  const request = api.get(cid, { signal })
  courses.set(cid, request)
  const clear = () => { if (courses.get(cid) === request) courses.delete(cid) }
  void request.then(clear, clear)
  return request
}
