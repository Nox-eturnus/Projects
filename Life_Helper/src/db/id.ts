/**
 * UUIDv7 (RFC 9562) generation. Decision 2 requires every entity's primary
 * key to be a client-generated UUIDv7 — never an autoincrement integer —
 * specifically because its leading 48 bits are a millisecond timestamp,
 * which makes ids generated on one device sort chronologically without a
 * server round trip. This is the first part that actually creates an
 * `items` row from the client, so it's the first part that needs this.
 */

const HEX_GROUPS = [4, 2, 2, 2, 6] as const

export function generateItemId(now: number = Date.now()): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)

  const ts = BigInt(Math.floor(now))
  bytes[0] = Number((ts >> 40n) & 0xffn)
  bytes[1] = Number((ts >> 32n) & 0xffn)
  bytes[2] = Number((ts >> 24n) & 0xffn)
  bytes[3] = Number((ts >> 16n) & 0xffn)
  bytes[4] = Number((ts >> 8n) & 0xffn)
  bytes[5] = Number(ts & 0xffn)

  // Version 7 in the high nibble of byte 6; variant `10` in the top two
  // bits of byte 8 — the two fixed bit patterns RFC 9562 defines, with the
  // remaining bits left as the CSPRNG output already in place.
  bytes[6] = (bytes[6] & 0x0f) | 0x70
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  let hex = ''
  for (const byte of bytes) hex += byte.toString(16).padStart(2, '0')

  const groups: string[] = []
  let offset = 0
  for (const groupLength of HEX_GROUPS) {
    groups.push(hex.slice(offset, offset + groupLength * 2))
    offset += groupLength * 2
  }
  return groups.join('-')
}
