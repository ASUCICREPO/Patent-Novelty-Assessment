#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { PatentNoveltyStack } from './patent-novelty-stack';

const app = new cdk.App();
new PatentNoveltyStack(app, 'PatentNoveltyStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});
