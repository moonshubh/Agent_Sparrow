import { Node, mergeAttributes } from "@tiptap/core";
import { getGlobalArtifactStore } from "@/features/librechat/artifacts/ArtifactContext";
import {
  findImageByTitle,
  resolveImageSrc,
} from "@/features/librechat/artifacts/imageUtils";

const ARTIFACT_DIRECTIVE_PATTERN = /^::artifact\{[^}]+\}/;

const escapeRegExp = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const getAttributeValue = (raw: string, key: string): string | undefined => {
  const escapedKey = escapeRegExp(key);
  const match = raw.match(new RegExp(`${escapedKey}=(?:"([^"]+)"|'([^']+)')`));
  return match ? match[1] || match[2] : undefined;
};

interface ArtifactDirectiveNode {
  attrs?: {
    raw?: string;
  };
}

export const ArtifactDirective = Node.create({
  name: "artifactDirective",

  group: "block",
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      raw: { default: "" },
      type: { default: "" },
      title: { default: "" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="artifact-directive"]',
        getAttrs: (element) => {
          if (!(element instanceof HTMLElement)) return false;
          const raw =
            element.getAttribute("data-raw") || element.textContent || "";
          const type = getAttributeValue(raw, "type") || "";
          const title = getAttributeValue(raw, "title") || "";
          return { raw, type, title };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const { raw, type, title, ...rest } = HTMLAttributes as {
      raw?: string;
      type?: string;
      title?: string;
      [key: string]: string | undefined;
    };

    if (type === "image") {
      const store = getGlobalArtifactStore();
      const artifactsById = store?.getState().artifactsById ?? {};
      const imageArtifact = title
        ? findImageByTitle(artifactsById, title)
        : undefined;
      const src = imageArtifact ? resolveImageSrc(imageArtifact) : null;

      if (src) {
        return [
          "div",
          mergeAttributes(rest, {
            "data-type": "artifact-directive",
            "data-raw": raw || "",
            contenteditable: "false",
            class:
              "lc-tiptap-artifact-directive lc-tiptap-artifact-directive-image",
          }),
          [
            "img",
            {
              src,
              alt: title || imageArtifact?.title || "Image",
            },
          ],
        ];
      }
    }

    const label = title
      ? `${title}${type ? ` (${type})` : ""}`
      : type
        ? `${type} artifact`
        : "artifact";

    return [
      "div",
      mergeAttributes(rest, {
        "data-type": "artifact-directive",
        "data-raw": raw || "",
        contenteditable: "false",
        class: "lc-tiptap-artifact-directive",
      }),
      `Artifact: ${label}`,
    ];
  },

  parseMarkdown: (token: { raw?: string }) => {
    const raw = token.raw || "";
    const type = getAttributeValue(raw, "type") || "";
    const title = getAttributeValue(raw, "title") || "";
    return {
      type: "artifactDirective",
      attrs: { raw, type, title },
    };
  },

  renderMarkdown: (node: ArtifactDirectiveNode) => {
    return node.attrs?.raw || "";
  },

  markdownTokenizer: {
    name: "artifactDirective",
    level: "block",
    start: (src: string) => src.indexOf("::artifact{"),
    tokenize: (src: string) => {
      const match = src.match(ARTIFACT_DIRECTIVE_PATTERN);
      if (!match) return undefined;
      return {
        type: "artifactDirective",
        raw: match[0],
        text: match[0],
      };
    },
  },
});

export default ArtifactDirective;
