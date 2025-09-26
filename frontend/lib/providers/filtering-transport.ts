import { DefaultChatTransport } from 'ai';
import type { UIMessage, UIMessageChunk } from 'ai';

const SYSTEM_REGEXES = [
  /<system>[\s\S]*?<\/system>/gi,
  /<internal>[\s\S]*?<\/internal>/gi,
  /<self_critique>[\s\S]*?<\/self_critique>/gi,
  /.*loyalty relationship.*/gi,
];

const stripSystemMarkers = (text: string): string => {
  let result = text;
  for (const pattern of SYSTEM_REGEXES) {
    result = result.replace(pattern, '');
  }
  return result;
};

export const filterUIMessageStream = (
  stream: ReadableStream<UIMessageChunk>,
): ReadableStream<UIMessageChunk> =>
  stream.pipeThrough(
    new TransformStream<UIMessageChunk, UIMessageChunk>({
      transform(chunk, controller) {
        if (chunk.type === 'text-delta' && typeof (chunk as any).delta === 'string') {
          const filtered = stripSystemMarkers((chunk as any).delta);
          if (filtered) {
            controller.enqueue({ ...chunk, delta: filtered } as UIMessageChunk);
          }
          return;
        }

        controller.enqueue(chunk);
      },
    }),
  );

export class FilteringChatTransport<UI_MESSAGE extends UIMessage> extends DefaultChatTransport<UI_MESSAGE> {
  protected processResponseStream(
    stream: ReadableStream<Uint8Array<ArrayBufferLike>>,
  ): ReadableStream<UIMessageChunk> {
    const baseStream = super.processResponseStream(stream);
    return filterUIMessageStream(baseStream);
  }
}

export { stripSystemMarkers };
