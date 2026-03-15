"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const uploadFile = async (fileToUpload: File) => {
    setFile(fileToUpload);
    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", fileToUpload);

    try {
      const res = await fetch("/api/upload-start", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError((data.error as string) || "Upload failed");
        setUploading(false);
        return;
      }

      const data = await res.json();
      const uploadId = data.uploadId;

      router.push(`/chat?uploadId=${uploadId}`);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = e.target.files?.[0];
    if (chosen) {
      setError(null);
      uploadFile(chosen);
    } else {
      setFile(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const item = e.dataTransfer.files?.[0];
    if (item && (item.type.startsWith("video/") || item.type.startsWith("image/"))) {
      setError(null);
      uploadFile(item);
    } else if (item) {
      setError("Please select a video or image file.");
      setFile(null);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center p-8">
      <div className="mb-8 text-center">
        <h1 className="mb-2 text-4xl font-bold tracking-tight text-text">
          Video<span className="text-primary">2</span>Site
        </h1>
        <p className="text-text-muted">
          Transform your screencast into a working site
        </p>
      </div>

      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`
          group relative w-full max-w-lg cursor-pointer rounded-2xl border-2 border-dashed
          p-12 text-center transition-all duration-200
          ${dragOver
            ? "border-primary bg-primary/10 shadow-[0_0_30px_rgba(37,99,235,0.15)]"
            : "border-border hover:border-primary/50 hover:bg-surface-raised/50"
          }
        `}
      >
        <div className="mb-4 flex justify-center">
          <svg
            className={`h-12 w-12 transition-colors duration-200 ${dragOver ? "text-primary" : "text-text-dim group-hover:text-text-muted"}`}
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
            />
          </svg>
        </div>

        <p className="mb-1 text-lg font-medium text-text">
          Drop an MP4 file here
        </p>
        <p className="mb-6 text-sm text-text-muted">or click to browse</p>

        <label
          className={`
            inline-flex cursor-pointer items-center gap-2 rounded-lg px-6 py-2.5
            text-sm font-medium text-white transition-all duration-200
            ${uploading
              ? "bg-text-dim cursor-not-allowed"
              : "bg-primary hover:bg-primary-hover active:scale-[0.98] shadow-[0_0_20px_rgba(37,99,235,0.2)]"
            }
          `}
        >
          {uploading ? (
            <>
              <svg
                className="h-4 w-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Uploading…
            </>
          ) : (
            "Choose File"
          )}
          <input
            type="file"
            onChange={handleFileChange}
            disabled={uploading}
            className="sr-only"
          />
        </label>

        {file && (
          <p className="mt-4 text-sm text-text-muted">
            {uploading ? (
              <span className="text-primary">{file.name}</span>
            ) : (
              <>Selected: {file.name}</>
            )}
          </p>
        )}
      </div>

      {error && (
        <div
          className="mt-6 flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
          role="alert"
        >
          <svg
            className="h-4 w-4 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
            />
          </svg>
          {error}
        </div>
      )}
    </main>
  );
}
