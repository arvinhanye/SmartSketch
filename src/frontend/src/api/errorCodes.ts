import type { components } from '../../../contracts/v1/generated/typescript/openapi'

type ErrorCode = components['schemas']['ErrorCode']

// 契约 ErrorCode 的运行时副本，用于校验错误体；下方类型断言保证与契约双向一致
const ERROR_CODES = [
  'UNAUTHENTICATED',
  'COURSE_FORBIDDEN',
  'ROLE_FORBIDDEN',
  'NOT_FOUND',
  'GRAPH_NOT_PUBLISHED',
  'UNSUPPORTED_FORMAT',
  'FILE_TOO_LARGE',
  'VALIDATION_ERROR',
  'CYCLE_DETECTED',
  'DANGLING_ENDPOINT',
  'DUPLICATE_RELATION',
  'NODE_LOCKED',
  'TASK_NOT_CANCELLABLE',
  'PUBLISH_BLOCKED',
  'RATE_LIMITED',
  'LLM_UNAVAILABLE',
  'DOCUMENT_UNREADABLE',
  'EXTRACTION_INCOMPLETE',
  'STORAGE_UNAVAILABLE',
  'INTERNAL_ERROR',
  'TASK_ATTEMPTS_EXHAUSTED',
  'PUBLISH_IN_PROGRESS',
  'COURSE_BUSY',
  'BUDGET_EXCEEDED',
  'DOCUMENT_NOT_DELETABLE',
  'REVISION_CONFLICT',
  'USERNAME_TAKEN',
  'MODEL_CONFIG_REQUIRED',
  'INVITE_CODE_INVALID',
  'ALREADY_MEMBER',
] as const satisfies readonly ErrorCode[]
type MissingErrorCode = Exclude<ErrorCode, (typeof ERROR_CODES)[number]>
const errorCodesComplete: [MissingErrorCode] extends [never] ? true : MissingErrorCode = true
void errorCodesComplete
const ERROR_CODE_SET: ReadonlySet<string> = new Set(ERROR_CODES)

export function isContractErrorCode(value: unknown): value is ErrorCode {
  return typeof value === 'string' && ERROR_CODE_SET.has(value)
}
