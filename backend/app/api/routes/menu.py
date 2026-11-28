from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.catalog import (
    CategoryRead,
    ExtraIn,
    ExtraRead,
    ExtraUpdate,
    MenuPhotoRead,
    PackageGroupIn,
    PackageGroupUpdate,
    PackageIn,
    PackageOptionIn,
    PackageRead,
    PackageUpdate,
    QuoteIn,
    QuoteRead,
    RecipeIn,
    RecipeItemIn,
    RecipePreview,
    RecipePreviewIn,
    RecipeRead,
    RecipeUpdate,
)
from app.services import menu_catalog
from app.services.menu_photos import save_menu_photo

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(
    session: SessionDep, _tenant: CurrentActiveTenant
) -> list[CategoryRead]:
    return await menu_catalog.list_service_categories(session)


@router.post(
    "/photos", response_model=MenuPhotoRead, status_code=status.HTTP_201_CREATED
)
async def upload_photo(
    tenant: CurrentActiveTenant, photo: UploadFile = File()
) -> MenuPhotoRead:
    url = await save_menu_photo(tenant.id, photo)
    return MenuPhotoRead(url=url)


@router.get("/recipes", response_model=list[RecipeRead])
async def list_recipes(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[RecipeRead]:
    return await menu_catalog.list_recipes(session, tenant.id)


@router.post("/recipes", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    session: SessionDep, tenant: CurrentActiveTenant, data: RecipeIn
) -> RecipeRead:
    recipe = await menu_catalog.create_recipe(session, tenant.id, data)
    await session.commit()
    return recipe


@router.get("/recipes/{recipe_id}", response_model=RecipeRead)
async def get_recipe(
    session: SessionDep, tenant: CurrentActiveTenant, recipe_id: UUID
) -> RecipeRead:
    for recipe in await menu_catalog.list_recipes(session, tenant.id):
        if recipe.id == recipe_id:
            return recipe
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró la receta"
    )


@router.patch("/recipes/{recipe_id}", response_model=RecipeRead)
async def update_recipe(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    recipe_id: UUID,
    data: RecipeUpdate,
) -> RecipeRead:
    recipe = await menu_catalog.update_recipe(session, tenant.id, recipe_id, data)
    await session.commit()
    return recipe


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    session: SessionDep, tenant: CurrentActiveTenant, recipe_id: UUID
) -> None:
    await menu_catalog.delete_recipe(session, tenant.id, recipe_id)
    await session.commit()


@router.post(
    "/recipes/{recipe_id}/items",
    response_model=RecipeRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_recipe_item(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    recipe_id: UUID,
    data: RecipeItemIn,
) -> RecipeRead:
    recipe = await menu_catalog.add_recipe_item(session, tenant.id, recipe_id, data)
    await session.commit()
    return recipe


@router.post("/recipes/{recipe_id}/preview", response_model=RecipePreview)
async def preview_recipe(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    recipe_id: UUID,
    data: RecipePreviewIn,
) -> RecipePreview:
    return await menu_catalog.preview_recipe(session, tenant.id, recipe_id, data.items)


@router.patch("/recipe-items/{item_id}", response_model=RecipeRead)
async def update_recipe_item(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    item_id: UUID,
    data: RecipeItemIn,
) -> RecipeRead:
    recipe = await menu_catalog.update_recipe_item(session, tenant.id, item_id, data)
    await session.commit()
    return recipe


@router.delete("/recipe-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe_item(
    session: SessionDep, tenant: CurrentActiveTenant, item_id: UUID
) -> None:
    await menu_catalog.delete_recipe_item(session, tenant.id, item_id)
    await session.commit()


@router.get("/packages", response_model=list[PackageRead])
async def list_packages(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[PackageRead]:
    return await menu_catalog.list_packages(session, tenant.id)


@router.post(
    "/packages", response_model=PackageRead, status_code=status.HTTP_201_CREATED
)
async def create_package(
    session: SessionDep, tenant: CurrentActiveTenant, data: PackageIn
) -> PackageRead:
    package = await menu_catalog.create_package(session, tenant.id, data)
    await session.commit()
    return package


@router.get("/packages/{package_id}", response_model=PackageRead)
async def get_package(
    session: SessionDep, tenant: CurrentActiveTenant, package_id: UUID
) -> PackageRead:
    for package in await menu_catalog.list_packages(session, tenant.id):
        if package.id == package_id:
            return package
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró el paquete"
    )


@router.patch("/packages/{package_id}", response_model=PackageRead)
async def update_package(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
    data: PackageUpdate,
) -> PackageRead:
    package = await menu_catalog.update_package(session, tenant.id, package_id, data)
    await session.commit()
    return package


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    session: SessionDep, tenant: CurrentActiveTenant, package_id: UUID
) -> None:
    await menu_catalog.delete_package(session, tenant.id, package_id)
    await session.commit()


@router.post(
    "/packages/{package_id}/groups",
    response_model=PackageRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_group(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
    data: PackageGroupIn,
) -> PackageRead:
    package = await menu_catalog.add_group(session, tenant.id, package_id, data)
    await session.commit()
    return package


@router.patch("/groups/{group_id}", response_model=PackageRead)
async def update_group(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    group_id: UUID,
    data: PackageGroupUpdate,
) -> PackageRead:
    package = await menu_catalog.update_group(session, tenant.id, group_id, data)
    await session.commit()
    return package


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    session: SessionDep, tenant: CurrentActiveTenant, group_id: UUID
) -> None:
    await menu_catalog.delete_group(session, tenant.id, group_id)
    await session.commit()


@router.post(
    "/groups/{group_id}/options",
    response_model=PackageRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_option(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    group_id: UUID,
    data: PackageOptionIn,
) -> PackageRead:
    package = await menu_catalog.add_option(session, tenant.id, group_id, data)
    await session.commit()
    return package


@router.delete("/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_option(
    session: SessionDep, tenant: CurrentActiveTenant, option_id: UUID
) -> None:
    await menu_catalog.delete_option(session, tenant.id, option_id)
    await session.commit()


@router.post("/packages/{package_id}/quote", response_model=QuoteRead)
async def quote_package(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
    data: QuoteIn,
) -> QuoteRead:
    return await menu_catalog.quote_for_package(session, tenant.id, package_id, data)


@router.get("/extras", response_model=list[ExtraRead])
async def list_extras(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[ExtraRead]:
    return await menu_catalog.list_extras(session, tenant.id)


@router.post("/extras", response_model=ExtraRead, status_code=status.HTTP_201_CREATED)
async def create_extra(
    session: SessionDep, tenant: CurrentActiveTenant, data: ExtraIn
) -> ExtraRead:
    extra = await menu_catalog.create_extra(session, tenant.id, data)
    await session.commit()
    return extra


@router.patch("/extras/{extra_id}", response_model=ExtraRead)
async def update_extra(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    extra_id: UUID,
    data: ExtraUpdate,
) -> ExtraRead:
    extra = await menu_catalog.update_extra(session, tenant.id, extra_id, data)
    await session.commit()
    return extra


@router.delete("/extras/{extra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extra(
    session: SessionDep, tenant: CurrentActiveTenant, extra_id: UUID
) -> None:
    await menu_catalog.delete_extra(session, tenant.id, extra_id)
    await session.commit()
