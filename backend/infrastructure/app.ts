#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { PdfProcessingStack } from './pdf-processing-stack';

const app = new cdk.App();
new PdfProcessingStack(app, 'PatentNoveltyPdfProcessingStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});
