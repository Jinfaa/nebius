"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          Upload video or image
        </h1>
        <p style={{ marginBottom: "1.5rem", color: "#666" }}>
          Drop a video or image here or click to choose
        </p>
        <input
          type="file"
          accept="video/*,image/*"
          onChange={handleFileChange}
          disabled={uploading}
          style={{ display: "block", margin: "0 auto 1rem" }}
        />
        {file && (
          <p style={{ marginBottom: 0, fontSize: "0.9rem" }}>
            {uploading ? `Processing ${file.name}…` : `Selected: ${file.name}`}
          </p>
        )}

        {uploading && (
          <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "#666" }}>
            Uploading…
          </p>
        )}
      </div>
      {error && (
        <p style={{ marginTop: "1rem", color: "#c00" }} role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
