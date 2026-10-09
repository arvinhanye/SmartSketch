/**
 * 入口图标的唯一来源：左侧导航与课程概览入口卡共用，一个去向只用一个图标、不同去向不共用图标。
 * 图标本身画在 `AppIcon.vue`；这里只决定“哪个去向用哪个图标”。
 */
export const DESTINATION_ICONS = {
  courses: 'home', // 我的课程（课程列表）
  overview: 'overview', // 课程概览
  materials: 'file', // 教学资料 / 上传与处理进度
  graph: 'graph', // 知识图谱（学生浏览 / 教师编辑草稿）
  review: 'check', // 审核与发布
  members: 'members', // 课程成员
  chat: 'chat', // 课程问答
  settings: 'key', // 模型 API 设置
  course: 'book', // 课程列表里的一门课程
} as const

export type Destination = keyof typeof DESTINATION_ICONS
