import {
  DEFAULT_ATTACHMENT_LIMITS,
  type AttachmentLimits,
} from "./attachment-limits";
import { classifyFile, isSvgFilename } from "./doc-attachments";
import {
  extractBase64FromDataUrl,
  readFileAsDataUrl,
} from "./file-attachments";

export interface PendingAttachment {
  type: string;
  filename: string;
  base64?: string;
  previewUrl?: string;
  size?: number;
  mimeType?: string;
}

export type AttachmentRejectReason = "unsupported" | "too_large" | "quota";

export interface AttachmentReject {
  name: string;
  reason: AttachmentRejectReason;
}

export async function fileToAttachment(
  file: File,
): Promise<PendingAttachment> {
  const raw = await readFileAsDataUrl(file);
  const svg = isSvgFilename(file.name) || file.type === "image/svg+xml";
  const isImage = !svg && file.type.startsWith("image/");
  return {
    type: isImage ? "image" : "file",
    filename: file.name,
    base64: extractBase64FromDataUrl(raw),
    previewUrl: isImage || svg ? raw : undefined,
    size: file.size,
    mimeType: file.type || undefined,
  };
}

export function filterAttachments(
  files: File[],
  currentAttachments: Array<{ size?: number }>,
  limits: AttachmentLimits = DEFAULT_ATTACHMENT_LIMITS,
): { accepted: File[]; rejected: AttachmentReject[] } {
  let runningTotal = currentAttachments.reduce(
    (sum, attachment) => sum + (attachment.size ?? 0),
    0,
  );
  const accepted: File[] = [];
  const rejected: AttachmentReject[] = [];
  for (const file of files) {
    if (!classifyFile(file)) {
      rejected.push({ name: file.name, reason: "unsupported" });
      continue;
    }
    if (file.size > limits.maxFileBytes) {
      rejected.push({ name: file.name, reason: "too_large" });
      continue;
    }
    if (runningTotal + file.size > limits.maxTotalBytes) {
      rejected.push({ name: file.name, reason: "quota" });
      break;
    }
    runningTotal += file.size;
    accepted.push(file);
  }
  return { accepted, rejected };
}
