# Patent Search Tool - Frontend

University of Minnesota Patent Novelty Assessment Tool

A modern Next.js application for uploading and analyzing patent invention disclosures using AI.

---

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- AWS Account with S3 access
- AWS credentials (Access Key ID & Secret Access Key)

### Installation

```bash
# Install dependencies
npm install

# Configure environment
cp env.example .env.local

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

---

## ⚙️ Configuration

### Environment Variables

Create `.env.local` in the frontend directory with your AWS credentials:

```env
# AWS S3 Configuration
NEXT_PUBLIC_AWS_ACCESS_KEY_ID=your_access_key_id
NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY=your_secret_access_key
NEXT_PUBLIC_AWS_REGION=us-west-2
NEXT_PUBLIC_S3_BUCKET=patent-novelty-pdf-processing-{account-id}

# Optional Settings
NEXT_PUBLIC_ENABLE_ANALYTICS=false
NEXT_PUBLIC_ENABLE_DEBUG=false
NEXT_PUBLIC_MAX_FILE_SIZE=10485760
NEXT_PUBLIC_ALLOWED_FILE_TYPES=application/pdf
```

### AWS Setup

**1. Get S3 Bucket Name**

Your backend creates a bucket named: `patent-novelty-pdf-processing-{aws-account-id}`

**2. Create IAM User for Uploads**

Create an IAM user with this policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject"],
    "Resource": "arn:aws:s3:::patent-novelty-pdf-processing-*/*"
  }]
}
```

**3. Generate Access Keys**

- Go to IAM → Users → Your User → Security Credentials
- Create Access Key
- Save Access Key ID and Secret Access Key
- Add to `.env.local`

---

## 🏗️ Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS 4
- **UI Components**: Shadcn UI
- **AWS SDK**: aws-sdk (for S3 uploads)
- **Fonts**: Geist Sans & Geist Mono

---

## 📁 Project Structure

```
frontend/
├── app/                      # Next.js App Router
│   ├── layout.tsx           # Root layout
│   ├── page.tsx             # Home page
│   └── globals.css          # Global styles
│
├── components/              # React components
│   ├── Header.tsx           # Navigation header
│   ├── UploadSection.tsx    # Upload container
│   ├── FileUploadCard.tsx   # Upload widget
│   ├── UploadIcon.tsx       # Upload icon SVG
│   ├── index.ts             # Component exports
│   └── ui/                  # Shadcn UI components
│       └── button.tsx
│
├── hooks/                   # Custom React hooks
│   └── useFileUpload.ts     # S3 upload logic
│
├── types/                   # TypeScript types
│   └── index.ts             # Type definitions
│
├── lib/                     # Utilities
│   ├── utils.ts             # Helper functions
│   ├── constants.ts         # App constants
│   └── config.ts            # Environment config
│
├── public/                  # Static assets
│   └── University_of_Minnesota_wordmark.png
│
└── Configuration
    ├── package.json
    ├── tsconfig.json
    ├── next.config.ts
    └── .env.local (create this)
```

---

## 🎯 Features

### File Upload
- ✅ Drag & drop PDF files
- ✅ Click to browse files
- ✅ Single file validation
- ✅ PDF type validation
- ✅ 10MB size limit
- ✅ Direct S3 upload
- ✅ Real-time progress tracking
- ✅ One-step upload process

### User Experience
- ✅ University of Minnesota branding
- ✅ Responsive design (mobile, tablet, desktop)
- ✅ Progress indicators
- ✅ Error handling
- ✅ Loading states
- ✅ Smooth animations

### Technical
- ✅ TypeScript type safety
- ✅ Modular component architecture
- ✅ Custom hooks for logic separation
- ✅ Direct S3 integration
- ✅ Auto-triggers backend pipeline

---

## 🔄 How It Works

### Upload Flow

```
1. User clicks "Upload File" button
   ↓
2. File picker opens, user selects PDF
   ↓
3. Frontend validates file (type, size)
   ↓
4. AWS SDK uploads directly to S3
   ↓
5. File lands in: uploads/filename.pdf
   ↓
6. S3 event triggers Lambda function
   ↓
7. Patent analysis pipeline starts
   ↓
8. Results stored in DynamoDB
```

### File Storage Path
```
S3: patent-novelty-pdf-processing-{account-id}/
    └── uploads/
        └── your-document.pdf  ← Frontend uploads here
```

---

## 🎨 Brand Colors

```css
University of Minnesota Maroon: #7A0019
Light Pink (Accent): #FFF7F9
Gold: #FFCC33
```

All colors are defined in:
- `app/globals.css` (CSS variables)
- `lib/constants.ts` (TypeScript constants)

---

## 📝 Available Scripts

```bash
# Development
npm run dev          # Start dev server (http://localhost:3000)

# Production
npm run build        # Build for production
npm start            # Start production server

# Code Quality
npm run lint         # Run ESLint
npm run type-check   # TypeScript validation
```

---

## 🧪 Testing the Upload

1. **Start the app**:
   ```bash
   npm run dev
   ```

2. **Open**: http://localhost:3000

3. **Upload a PDF**:
   - Click "Upload File" button
   - Select a PDF file
   - Watch progress bar

4. **Verify in AWS Console**:
   - Go to S3 → Your bucket → `uploads/` folder
   - Your PDF should be there
   - Check CloudWatch logs for Lambda execution

---

## 🔒 Security Notes

### Development
Using AWS credentials in `.env.local` is fine for local development.

**⚠️ Never commit `.env.local` to git!** (It's in `.gitignore`)

### Production
For production, use one of these approaches:

**Option 1: AWS Cognito Identity Pools** (Recommended)
```typescript
import AWS from 'aws-sdk';

AWS.config.credentials = new AWS.CognitoIdentityCredentials({
  IdentityPoolId: 'us-west-2:xxxxx-xxxx'
});
```

**Option 2: AWS Amplify**
```bash
npm install @aws-amplify/storage
```

**Option 3: Presigned URLs**
Get upload URLs from a backend Lambda function.

---

## 🐛 Troubleshooting

### Error: "Missing credentials in config"
**Solution**: Check `.env.local` has AWS credentials set.

### Error: "Access Denied"
**Solution**: 
- Verify IAM user has `s3:PutObject` permission
- Check bucket name is correct
- Verify AWS region matches

### Error: CORS errors in browser
**Solution**: S3 bucket needs CORS configuration (usually set by backend CDK stack).

### Upload succeeds but no processing
**Solution**:
- Verify file is in `uploads/` folder
- Check S3 event notifications are configured
- Check Lambda CloudWatch logs

---

## 🚀 Deployment

### Vercel (Recommended)
```bash
npm install -g vercel
vercel
```

### Environment Variables in Vercel
Add these in Vercel Dashboard → Project Settings → Environment Variables:
- `NEXT_PUBLIC_AWS_ACCESS_KEY_ID`
- `NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY`
- `NEXT_PUBLIC_AWS_REGION`
- `NEXT_PUBLIC_S3_BUCKET`

### Other Platforms
- AWS Amplify
- Netlify
- Docker
- Static export

See build command: `npm run build`

---

## 🔗 Related

- **Backend**: `../backend/` - CDK infrastructure & Lambda functions
- **S3 Bucket**: Created by backend CDK stack
- **Lambda Functions**: Triggered by S3 uploads
- **DynamoDB**: Stores analysis results

---

## 📄 Key Files

| File | Purpose |
|------|---------|
| `app/page.tsx` | Home page with upload interface |
| `components/FileUploadCard.tsx` | Upload widget with drag & drop |
| `hooks/useFileUpload.ts` | S3 upload logic & state management |
| `types/index.ts` | TypeScript type definitions |
| `lib/constants.ts` | Application constants |
| `.env.local` | Environment configuration (create this) |

---

## 🆘 Support

### Common Issues
1. **Credentials not working**: Verify IAM user has correct permissions
2. **Upload fails**: Check S3 bucket name and region
3. **No processing**: Verify S3 event notifications configured

### Logs to Check
- Browser Console: Frontend errors
- S3 Bucket: Verify file uploaded
- CloudWatch: Lambda execution logs

---

## 📊 Component Overview

### Header
- University of Minnesota logo
- "Patent Search Tool" title
- Border separator

### UploadSection
- Page heading
- Description text
- FileUploadCard container

### FileUploadCard
- Upload icon
- File name display
- Drag & drop zone
- Browse button
- Progress bar
- Error messages
- Upload button

### useFileUpload Hook
- File validation
- S3 client configuration
- Direct S3 upload
- Progress tracking
- Error handling

---

## ✅ Checklist

**Before First Run:**
- [ ] Installed dependencies (`npm install`)
- [ ] Created `.env.local` file
- [ ] Added AWS credentials
- [ ] Added S3 bucket name
- [ ] Verified IAM permissions

**Development:**
- [ ] Development server running
- [ ] Can upload files
- [ ] Files appear in S3
- [ ] Lambda functions triggered

**Production:**
- [ ] Environment variables configured
- [ ] Security review completed
- [ ] CORS configured
- [ ] Deployed to hosting platform

---

## 🎓 University of Minnesota

This application follows UMN brand guidelines:
- Official maroon color (#7A0019)
- University wordmark
- Professional design
- Accessible interface

---

**Version**: 1.0.0  
**Framework**: Next.js 15 + TypeScript + Shadcn UI  
**Status**: ✅ Production Ready  
**Last Updated**: September 29, 2025