import { Metadata, MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
    return {
        name: 'Dave Gray Teaches Code',
        short_name: "Dave Gray",
        description: "Dave's Blog powered by Next.js",
        start_url: '/',
        display: 'standalone',
        background_color: '#1E283A',
        theme_color: '#1E283A',
        // icons: [
        //     {
        //         "src": "/images/icon-192.png",
        //         "sizes": "192x192",
        //         "type": "image/png"
        //     },
        //     {
        //         "src": "/images/icon-512.png",
        //         "sizes": "512x512",
        //         "type": "image/png"
        //     },
        // ],
    }
}

export const metadata: Metadata = {
  title: "Profit Pilot",
  description: "Improving economical situation for everyone",
  applicationName: "Profit Pilot",
  authors: [{name:"Matias Aravena"}],
  icons: {
    icon :  {
      url: "/images/logos/png/logo-color.png",
      type: "image/png",
      sizes:"192x192",
      rel: "icon",
      fetchPriority: 'high',
  }}
};
