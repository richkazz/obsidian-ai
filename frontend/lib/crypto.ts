import CryptoJS from "crypto-js";

function getEncryptionKey(): string {
  if (
    typeof window !== "undefined" &&
    (window as any).__ENV?.NEXT_PUBLIC_ENCRYPTION_KEY !== undefined
  ) {
    return (window as any).__ENV.NEXT_PUBLIC_ENCRYPTION_KEY;
  }
  return process.env.NEXT_PUBLIC_ENCRYPTION_KEY || "";
}

export function encryptPayload(data: object): string {
  const jsonString = JSON.stringify(data);
  const key = getEncryptionKey();
  const encrypted = CryptoJS.AES.encrypt(jsonString, key).toString();
  return encrypted;
}
