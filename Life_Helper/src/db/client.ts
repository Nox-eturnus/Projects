/**
 * Main-thread API. Exactly one tab at a time ("the leader") holds the real
 * Worker with the OPFS-backed SQLite connection — see the module doc
 * comment in worker.ts and docs/phase_A3_db_layer.md for why: the OPFS SAH
 * pool VFS this project uses explicitly does not support multi-tab
 * concurrency, and this environment's SharedWorker was found to lack
 * `createSyncAccessHandle` (the browser gap is documented in
 * docs/phase_A3_db_layer.md), so a SharedWorker-based single-connection
 * design wasn't reliable enough to build on.
 *
 * Leadership is decided with the Web Locks API: the first tab to acquire
 * `LOCK_NAME` creates the Worker; every other tab becomes a follower and
 * relays mutate()/query() calls to the leader over a BroadcastChannel. If
 * the leader tab closes, its lock is released automatically and exactly
 * one waiting follower is promoted, which then creates its own Worker.
 */
import * as Comlink from 'comlink'
import type { WorkerApiImpl } from './worker.js'
import type { MutateInput, MutateResult, ReplayComparisonResult, TableName } from './ops.js'

const LOCK_NAME = 'life-helper-db-writer'
const CHANNEL_NAME = 'life-helper-db'
const REQUEST_TIMEOUT_MS = 10_000

type RemoteWorkerApi = Comlink.Remote<WorkerApiImpl>
type ChangeCallback = (tables: TableName[]) => void
type RequestOp = 'mutate' | 'query' | 'getDeviceId' | 'verifyReplay'

interface RequestMessage {
  type: 'request'
  requestId: string
  op: RequestOp
  payload: unknown
}
interface ResponseMessage {
  type: 'response'
  requestId: string
  ok: boolean
  result?: unknown
  error?: string
}
interface ChangeMessage {
  type: 'change'
  tables: TableName[]
}
type ChannelMessage = RequestMessage | ResponseMessage | ChangeMessage

interface PendingRequest {
  op: RequestOp
  payload: unknown
  resolve: (value: unknown) => void
  reject: (error: Error) => void
}

export class DbClient {
  private readonly channel = new BroadcastChannel(CHANNEL_NAME)
  private role: 'leader' | 'follower' | 'pending' = 'pending'
  private api?: RemoteWorkerApi
  private deviceId = ''
  private readonly ready: Promise<void>
  private readonly pending = new Map<string, PendingRequest>()
  private readonly listeners = new Set<ChangeCallback>()

  constructor() {
    this.channel.onmessage = (event: MessageEvent<ChannelMessage>) => {
      this.handleMessage(event.data)
    }
    this.ready = this.init()
  }

  private async init(): Promise<void> {
    const acquiredImmediately = await new Promise<boolean>((resolveAcquired) => {
      void navigator.locks.request(LOCK_NAME, { ifAvailable: true }, (lock) => {
        if (!lock) {
          resolveAcquired(false)
          return Promise.resolve()
        }
        resolveAcquired(true)
        // Hold this same grant for as long as the tab stays open — released
        // automatically by the browser when the tab closes.
        return new Promise<void>(() => {})
      })
    })

    if (acquiredImmediately) {
      await this.setUpAsLeader()
    } else {
      this.role = 'follower'
      this.waitForPromotion().catch((error: unknown) => {
        // Not swallowed: a stuck promotion would otherwise leave this tab
        // holding the lock forever while never actually serving requests,
        // silently timing out every pending sendToLeader() call instead of
        // surfacing why.
        console.error('DbClient: promotion to leader failed', error)
      })
    }
  }

  private async waitForPromotion(): Promise<void> {
    await new Promise<void>((resolveEntered) => {
      void navigator.locks.request(LOCK_NAME, () => {
        resolveEntered()
        return new Promise<void>(() => {})
      })
    })
    await this.setUpAsLeader()
  }

  private async setUpAsLeader(): Promise<void> {
    const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
    const api = Comlink.wrap<WorkerApiImpl>(worker)
    this.api = api
    const { deviceId } = await api.init()
    this.deviceId = deviceId
    await api.onChange(
      Comlink.proxy((tables: TableName[]) => {
        this.notifyLocal(tables)
        this.channel.postMessage({ type: 'change', tables } satisfies ChannelMessage)
      }),
    )
    this.role = 'leader'

    // Requests this tab sent to "the leader" while it was still a
    // follower, now stuck waiting for a reply that will never come: a
    // BroadcastChannel never delivers a message back to the sender that
    // posted it, so if THIS tab is the one that gets promoted, nothing
    // would otherwise answer its own still-pending request. Serve them
    // directly instead of leaving them to time out.
    const stillPending = [...this.pending.entries()]
    for (const [requestId, entry] of stillPending) {
      this.pending.delete(requestId)
      this.executeLocally(entry.op, entry.payload).then(entry.resolve, entry.reject)
    }
  }

  private async executeLocally(op: RequestOp, payload: unknown): Promise<unknown> {
    if (!this.api)
      throw new Error('DbClient.executeLocally() called before the leader worker was ready')
    if (op === 'mutate') return this.api.mutate(payload as MutateInput)
    if (op === 'query') {
      const { sql, params } = payload as { sql: string; params: unknown[] }
      return this.api.query(sql, params)
    }
    if (op === 'verifyReplay') return this.api.verifyReplay()
    return this.api.getDeviceId()
  }

  private handleMessage(message: ChannelMessage): void {
    if (message.type === 'change') {
      this.notifyLocal(message.tables)
      return
    }
    if (message.type === 'request') {
      if (this.role === 'leader') void this.serveRequest(message)
      return
    }
    const entry = this.pending.get(message.requestId)
    if (!entry) return
    this.pending.delete(message.requestId)
    if (message.ok) entry.resolve(message.result)
    else entry.reject(new Error(message.error ?? 'db request failed'))
  }

  private async serveRequest(message: RequestMessage): Promise<void> {
    if (!this.api) return
    try {
      const result = await this.executeLocally(message.op, message.payload)
      this.channel.postMessage({
        type: 'response',
        requestId: message.requestId,
        ok: true,
        result,
      } satisfies ChannelMessage)
    } catch (error) {
      this.channel.postMessage({
        type: 'response',
        requestId: message.requestId,
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      } satisfies ChannelMessage)
    }
  }

  private sendToLeader(op: RequestOp, payload: unknown): Promise<unknown> {
    const requestId = crypto.randomUUID()
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(requestId)
        reject(new Error(`db request "${op}" timed out waiting for the leader tab`))
      }, REQUEST_TIMEOUT_MS)
      this.pending.set(requestId, {
        op,
        payload,
        resolve: (value) => {
          clearTimeout(timeout)
          resolve(value)
        },
        reject: (error) => {
          clearTimeout(timeout)
          reject(error)
        },
      })
      this.channel.postMessage({ type: 'request', requestId, op, payload } satisfies ChannelMessage)
    })
  }

  private notifyLocal(tables: TableName[]): void {
    for (const listener of this.listeners) listener(tables)
  }

  async mutate(input: MutateInput): Promise<MutateResult> {
    await this.ready
    if (this.role === 'leader' && this.api) return this.api.mutate(input)
    return this.sendToLeader('mutate', input) as Promise<MutateResult>
  }

  async query<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T[]> {
    await this.ready
    if (this.role === 'leader' && this.api) return this.api.query(sql, params) as Promise<T[]>
    return this.sendToLeader('query', { sql, params }) as Promise<T[]>
  }

  async getDeviceId(): Promise<string> {
    await this.ready
    if (this.role === 'leader') return this.deviceId
    return this.sendToLeader('getDeviceId', undefined) as Promise<string>
  }

  /** Part B4's capture gate: verifies ops replay against this device's real
   * data. See worker.ts's verifyReplay() doc comment. */
  async verifyReplay(): Promise<ReplayComparisonResult> {
    await this.ready
    if (this.role === 'leader' && this.api) return this.api.verifyReplay()
    return this.sendToLeader('verifyReplay', undefined) as Promise<ReplayComparisonResult>
  }

  /** Local, same-tab, synchronous pub/sub — no BroadcastChannel/Comlink involved. */
  subscribe(listener: ChangeCallback): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
}

export const dbClient = new DbClient()
