/** jsdom does not implement native dialog modality/focus trapping. */
export function mockNativeDialog(): () => void {
  const prototype = HTMLDialogElement.prototype;
  const show = Object.getOwnPropertyDescriptor(prototype, 'showModal');
  const close = Object.getOwnPropertyDescriptor(prototype, 'close');
  Object.defineProperty(prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', ''); } });
  Object.defineProperty(prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open'); } });
  return () => {
    if (show) Object.defineProperty(prototype, 'showModal', show);
    else delete (prototype as unknown as Record<string, unknown>).showModal;
    if (close) Object.defineProperty(prototype, 'close', close);
    else delete (prototype as unknown as Record<string, unknown>).close;
  };
}
