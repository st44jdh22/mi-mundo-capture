// Staged transport only. No provider SDK, saved credentials or routing logic.
export class CaptureClient {
  constructor({endpoint, token, fetchImpl = globalThis.fetch, timeoutMs = 30000, testLoopback = false}) {
    const url = new URL(endpoint);
    const loopback = testLoopback && url.protocol === 'http:' && url.hostname === '127.0.0.1';
    if ((url.protocol !== 'https:' && !loopback) || url.username || url.password ||
        url.search || url.hash || url.pathname !== '/') throw new Error('Use an HTTPS receiver origin');
    if (typeof token !== 'string' || token.length < 32 || /[\r\n]/.test(token)) throw new Error('Invalid session token');
    this.origin = url.origin;
    this.token = token; // Memory only. Never localStorage, URL, log or app source.
    this.fetch = fetchImpl;
    this.timeoutMs = timeoutMs;
    this.pending = new Map();
    this.busy = false;
  }

  async request(path, options) {
    if (!this.token) throw new Error('Receiver session disconnected');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await this.fetch(this.origin + path, {
        ...options, headers: {...options?.headers, Authorization: 'Bearer ' + this.token},
        signal: controller.signal, redirect: 'error', credentials: 'omit', cache: 'no-store'
      });
    } finally { clearTimeout(timer); }
  }

  check(receipt, id, digest) {
    if (!receipt || receipt.job_id !== id || receipt.package_sha256 !== digest ||
        receipt.status !== 'RECEIVED_TEST_ONLY' || !receipt.receipt_id ||
        receipt.routed !== false || receipt.departmental_updates !== false ||
        receipt.production_evidence_filed !== false) throw new Error('Receipt does not match this test job');
    return receipt;
  }

  async lookup(id, digest) {
    const response = await this.request('/v1/jobs/' + id, {method: 'GET'});
    if (response.status === 404) return null;
    if (!response.ok) throw new Error('Receipt lookup failed (' + response.status + ')');
    return this.check(await response.json(), id, digest);
  }

  async transmit(id, blob) {
    if (this.busy) throw new Error('A job is already being checked');
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)) throw new Error('Invalid job ID');
    if (!(blob instanceof Blob) || !blob.size || blob.size > 100 * 1024 * 1024) throw new Error('Test job must be between 1 byte and 100 MiB');
    this.busy = true;
    try {
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())),
        b => b.toString(16).padStart(2, '0')).join('');
      const prior = this.pending.get(id);
      if (prior && prior.digest !== digest) throw new Error('Job changed: retain the previous package and use a new job ID');
      const snapshot = prior || {digest, blob};
      this.pending.set(id, snapshot);
      // Lookup first, including after an uncertain PUT or page-level retry.
      let receipt = await this.lookup(id, digest);
      if (receipt) return receipt;
      let uploaded;
      try {
        uploaded = await this.request('/v1/jobs/' + id, {
          method: 'PUT', headers: {'Content-Type': 'application/zip'}, body: snapshot.blob
        });
      } catch {
        // A timeout is not proof of failure. Reconcile; never blindly resend.
        receipt = await this.lookup(id, digest);
        if (receipt) return receipt;
        throw new Error('Upload not confirmed. Keep this job and check again.');
      }
      if (!uploaded.ok) throw new Error('Upload rejected (' + uploaded.status + '); keep this job');
      this.check(await uploaded.json(), id, digest);
      receipt = await this.lookup(id, digest);
      if (!receipt) throw new Error('Upload receipt is not independently readable; keep this job');
      return receipt;
    } finally { this.busy = false; }
  }

  disconnect() { this.token = ''; this.pending.clear(); }
}
