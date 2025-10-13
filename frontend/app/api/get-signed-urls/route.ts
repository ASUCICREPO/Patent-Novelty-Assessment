import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const filename = searchParams.get('filename');
    
    if (!filename) {
      return NextResponse.json({ error: 'Filename required' }, { status: 400 });
    }

    // Initialize S3 client with environment variables
    const s3Client = new S3Client({
      region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
      credentials: {
        accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID || "",
        secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY || "",
      },
    });

    const bucketName = process.env.NEXT_PUBLIC_S3_BUCKET;
    if (!bucketName) {
      return NextResponse.json({ error: 'S3 bucket name not configured' }, { status: 500 });
    }

    // Clean filename (remove .pdf extension if present)
    const cleanFilename = filename.replace(/\.pdf$/i, "");
    
    // Generate signed URLs for both reports
    const ptlsKey = `reports/${cleanFilename}_report.pdf`;
    const ecaKey = `reports/${cleanFilename}_eca_report.pdf`;

    console.log(`Generating signed URLs for ${cleanFilename}:`);
    console.log(`- PTLS: ${ptlsKey}`);
    console.log(`- ECA: ${ecaKey}`);

    // Generate signed URLs (valid for 1 hour)
    const [ptlsUrl, ecaUrl] = await Promise.all([
      getSignedUrl(s3Client, new GetObjectCommand({
        Bucket: bucketName,
        Key: ptlsKey,
      }), { expiresIn: 3600 }), // 1 hour
      getSignedUrl(s3Client, new GetObjectCommand({
        Bucket: bucketName,
        Key: ecaKey,
      }), { expiresIn: 3600 }), // 1 hour
    ]);

    console.log(`Generated signed URLs successfully`);

    return NextResponse.json({
      ptlsUrl,
      ecaUrl,
      filename: cleanFilename
    });

  } catch (error) {
    console.error('Error generating signed URLs:', error);
    return NextResponse.json(
      { error: 'Failed to generate signed URLs', details: error instanceof Error ? error.message : 'Unknown error' }, 
      { status: 500 }
    );
  }
}
