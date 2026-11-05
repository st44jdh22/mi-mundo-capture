// HS-META-001: UI/transport boundary only. No Meta SDK, phone bridge or network.
export const MODES = Object.freeze(['photo', 'video', 'audio']);

export class CaptureController {
  constructor(bridge, notify = () => {}) {
    this.bridge = bridge;
    this.notify = notify;
    this.capture = null;
    this.state = 'NOT_CONNECTED';
    this.message = 'Native glasses capture is not connected.';
  }

  update(state, message) {
    this.state = state;
    this.message = message;
    this.notify({state, message, hasCapture: Boolean(this.capture)});
  }

  async choose(kind) {
    if (!MODES.includes(kind)) throw new Error('Unsupported capture mode');
    if (this.state === 'CAPTURING' || this.state === 'SENDING') throw new Error('Another operation is in progress');
    // Never lose a retained original because the user presses a different mode.
    if (this.capture && this.state !== 'RECEIVED_TEST_ONLY') {
      this.update('RETAINED', 'An unsent capture is retained. Send or recover it before starting another.');
      return;
    }
    this.update('CAPTURING', kind.toUpperCase() + ': checking glasses access…');
    try {
      if (!this.bridge?.capture) throw new Error('SDK capture bridge is not connected.');
      const item = await this.bridge.capture(kind);
      if (!item || item.kind !== kind || typeof item.id !== 'string' || !item.id ||
          !Number.isSafeInteger(item.bytes) || item.bytes <= 0 ||
          typeof item.mimeType !== 'string' || !item.mimeType) {
        throw new Error('No verifiable media returned by the capture bridge.');
      }
      this.capture = item;
      this.update('READY_TO_SEND', kind.toUpperCase() + ' retained. Send when ready.');
    } catch (error) {
      this.update('BLOCKED', error instanceof Error ? error.message : 'Capture unavailable.');
    }
  }

  async send() {
    if (!this.capture) {
      this.update('BLOCKED', 'Nothing captured. No file was sent.');
      return;
    }
    if (this.state === 'SENDING' || this.state === 'CAPTURING') return;
    const original = this.capture;
    this.update('SENDING', 'Sending… receipt and readback required.');
    try {
      if (!this.bridge?.transmit || !this.bridge?.verifyReceipt) throw new Error('Private intake bridge is not connected.');
      const receipt = await this.bridge.transmit(original);
      // Independently query/verify stored original; a PUT response is not enough.
      const verified = await this.bridge.verifyReceipt(original, receipt);
      if (verified !== true) throw new Error('Destination readback not verified. Original retained.');
      if (receipt.status !== 'RECEIVED_TEST_ONLY') throw new Error('Only isolated synthetic receipts are supported by this prototype.');
      this.update('RECEIVED_TEST_ONLY', 'Synthetic intake readback verified. Not a live upload.');
    } catch (error) {
      this.update('UNCONFIRMED', (error instanceof Error ? error.message : 'Upload unconfirmed.') + ' Original retained.');
    }
  }
}
