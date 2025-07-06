
export interface Route {
    name: string
    url: string
}

export const routes: Route[] = [
    { name: "Product", url: '/products' },
    { name: "Features", url: '/features' },
    { name: "Pricing", url: '/pricing' },
    { name: "About Us", url: '/about' },
    // { name: "Product 1", url: '/components/products/1' },
]
