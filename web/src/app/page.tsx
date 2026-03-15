"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = e.target.files?.[0];
    if (chosen) {
      setFile(chosen);
      setError(null);
    } else {
      setFile(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const item = e.dataTransfer.files?.[0];
    if (item?.type === "video/mp4") {
      setFile(item);
      setError(null);
    } else if (item) {
      setError("Please select an MP4 video file.");
      setFile(null);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select an MP4 video file first.");
      return;
    }
    setUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("output", "./plan");

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError((data.error as string) || "Upload failed");
        setUploading(false);
        return;
      }
      const jobId = data.jobId as string | undefined;
      if (jobId) {
        router.push(`/status?jobId=${encodeURIComponent(jobId)}`);
      } else {
        router.push("/status");
      }
    } catch {
      setError("Network error. Please try again.");
      setUploading(false);
    }
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
      }}
    >
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        style={{
          border: "2px dashed #ccc",
          borderRadius: "8px",
          padding: "3rem",
          textAlign: "center",
          minWidth: "320px",
          maxWidth: "480px",
          backgroundColor: "#fafafa",
        }}
      >
        <h1 style={{ marginBottom: "1rem", fontSize: "1.5rem" }}>
          Upload screencast video
        </h1>
        <p style={{ marginBottom: "1.5rem", color: "#666" }}>
          Drop an MP4 file here or click to choose
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept="video/mp4"
          onChange={handleFileChange}
          style={{ display: "block", margin: "0 auto 1rem" }}
        />
        {file && (
          <p style={{ marginBottom: "1rem", fontSize: "0.9rem" }}>
            Selected: {file.name}
          </p>
        )}
        <button
          type="button"
          onClick={handleUpload}
          disabled={uploading || !file}
          style={{
            padding: "0.5rem 1.5rem",
            fontSize: "1rem",
            cursor: uploading || !file ? "not-allowed" : "pointer",
            opacity: uploading || !file ? 0.6 : 1,
          }}
        >
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </div>
      {error && (
        <p style={{ marginTop: "1rem", color: "#c00" }} role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
