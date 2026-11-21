import {mkdir,writeFile} from 'node:fs/promises';

// Remote QA reads this from the frontend and compares it to the separately deployed API.
const commit=process.env.VERCEL_GIT_COMMIT_SHA;
if(commit){
  if(!/^[a-f0-9]{40}$/.test(commit))throw new Error('Invalid Vercel Git revision');
  await mkdir('dist/.well-known',{recursive:true});
  await writeFile('dist/.well-known/capzoryx-website.json',JSON.stringify({commit})+'\n');
}
