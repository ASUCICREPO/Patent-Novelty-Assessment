import { S3Client, HeadObjectCommand } from "@aws-sdk/client-s3";
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
    
    // Check for both reports
    const ptlsKey = `reports/${cleanFilename}_report.pdf`;
    const ecaKey = `reports/${cleanFilename}_eca_report.pdf`;

    console.log(`Checking reports for ${cleanFilename}:`);
    console.log(`- Bucket: ${bucketName}`);
    console.log(`- PTLS: ${ptlsKey}`);
    console.log(`- ECA: ${ecaKey}`);
    console.log(`- AWS Credentials: ${!!process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID}`);

    const [ptlsResponse, ecaResponse] = await Promise.allSettled([
      s3Client.send(new HeadObjectCommand({
        Bucket: bucketName,
        Key: ptlsKey,
      })),
      s3Client.send(new HeadObjectCommand({
        Bucket: bucketName,
        Key: ecaKey,
      })),
    ]);

    console.log(`PTLS Response:`, ptlsResponse);
    console.log(`ECA Response:`, ecaResponse);

    const ptlsReady = ptlsResponse.status === 'fulfilled';
    const ecaReady = ecaResponse.status === 'fulfilled';

    console.log(`Report status: PTLS=${ptlsReady}, ECA=${ecaReady}`);

    return NextResponse.json({
      ptlsReady,
      ecaReady,
      filename: cleanFilename
    });

  } catch (error) {
    console.error('Error checking reports:', error);
    return NextResponse.json(
      { error: 'Failed to check reports', details: error instanceof Error ? error.message : 'Unknown error' }, 
      { status: 500 }
    );
  }
}
